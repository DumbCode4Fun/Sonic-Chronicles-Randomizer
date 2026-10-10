"""
A GDB Remote Serial Protocol client, in pure Python, for melonDS' debug stub.

**Why this exists rather than `gdb-multiarch`.** Two questions in this project are behind
the ARM9 wall and neither can be answered from data: party-relative enemy scaling needs
the address where combat loads a creature's stats, and re-ordering recruitment needs the
code that reacts to a plot flag. Both are "set a watchpoint, trigger the thing, look at
the program counter" - and that is a handful of RSP packets, not a debugger session. A
toolchain install (devkitARM, or a gdb built for ARM) is a 1 GB dependency for something
the standard library can do in 300 lines, and this project has kept itself to the standard
library everywhere else.

It also makes the experiments **scriptable and repeatable**, which interactive gdb is not:
an experiment is a file in `tools/recon/`, it runs the same way twice, and what it found
can be pasted into the log.

Setting up melonDS
------------------
1. Config -> Emu settings -> Devtools -> **Enable GDB stub**, and **read the port out of
   that dialog**. The familiar 3333/3334 are the ports in BlocksDS' *DeSmuME* example;
   their melonDS instructions say to use the port the melonDS GUI shows. 3333 is this
   module's default and every entry point takes a port argument. "Break on startup" is
   optional and usually unhelpful here - we want to attach once the game is running.
2. **Turn the JIT off** (Config -> Emu settings -> CPU emulation). Single-stepping and
   breakpoints do not work reliably with it on.
3. Load the ROM, play to the point just before the thing you want to catch, then attach.

Known stub limitations, from melonDS' own documentation: data aborts and exceptions are
not reported to GDB, and not every packet a full gdb would send is implemented. This
client therefore asks for very little and checks what it gets.

**Whether melonDS runs this game well enough is not established.** The project plays on
DeSmuME 0.9.11 because newer builds misbehave with it, and DeSmuME 0.9.11 has no GDB stub
(checked: no stub strings in the shipped binary). So the first run of any experiment here
is also a compatibility test, and `probe()` reports enough to tell whether the game is
actually running rather than sitting at a white screen.

Protocol notes
--------------
Packets are ``$<payload>#<two hex checksum digits>``, the checksum a plain sum of the
payload bytes mod 256. The peer acknowledges with ``+`` (or ``-`` to ask for a resend).
``$O<hex>`` packets are console output from the target and may arrive at any time; they
are collected rather than mistaken for replies. A stop reply is ``S<aa>`` or
``T<aa><key>:<value>;...``, and for a watchpoint hit the keys are ``watch``, ``rwatch``
or ``awatch`` with the address that was accessed.

ARM register order in ``g``/``G`` is r0-r15 then CPSR, each four bytes little-endian;
r15 is the PC and the value this project cares about most.
"""
import binascii
import os
import socket
import struct
import sys
import time

#: melonDS' defaults.
ARM9_PORT, ARM7_PORT = 3333, 3334
#: Main RAM on a DS. The ARM9 binary is loaded at 0x02000000 (see KNOWN_MEMORY.md).
MAIN_RAM = (0x02000000, 0x02400000)

#: `Z`/`z` kinds.
BP_SOFT, BP_HARD, WP_WRITE, WP_READ, WP_ACCESS = 0, 1, 2, 3, 4


class GdbError(RuntimeError):
    pass


#: Nothing listening is the overwhelmingly common first failure, and a socket traceback
#: explains none of it. Say what it means and what to do instead.
#: The stub accepted us and then hung up. Past the "is it even running" stage, so the
#: advice is different.
DROPPED = """the stub %s mid-conversation.

**Most likely: the stub is wedged and melonDS needs restarting.** Observed 2026-10-10 -
once a client had connected with a bad handshake, the ARM9 stub on 3333 never recovered.
It kept accepting connections and then resetting them, answering less each attempt until
it went silent. Meanwhile the ARM7 stub on 3334, which nothing had touched, answered the
identical handshake from the identical client perfectly. A stub that has been mishandled
once stays broken for the life of the process.

Close melonDS, reopen it, load the ROM, get in-game, and connect ONCE.

If it still drops after a clean restart:

  1. Is melonDS still running? A reset can also mean the process went away.
  2. Re-run with tracing to see how far the conversation got:
         py tools/recon/gdbstub.py probe --trace
     Every byte in both directions is printed, which is the only view of it from this
     side - the stub's own log is not visible here.
  3. Try ARM7 as a control: py tools/recon/gdbstub.py probe 3334
     If ARM7 answers and ARM9 does not, the client is fine and the stub is the problem.
  4. Only one client at a time. A previous run still holding the socket will do this."""

NOT_LISTENING = """nothing is listening on %s:%d (%s)

That is what you get when melonDS is not running with its GDB stub enabled - it is
not a fault in this script. Check, in order:

  1. melonDS is actually running, with a ROM loaded and the game on screen.
  2. Config -> Emu settings -> Devtools -> "Enable GDB stub" is ticked, and the
     emulator has been restarted since (the stub only opens its socket at startup).
  3. The port matches the one that dialog shows. Pass it as an argument if it differs:
         py tools/recon/gdbstub.py probe <port>
  4. Config -> Emu settings -> CPU emulation -> the JIT recompiler is OFF, or
     stepping and breakpoints misbehave later even once this connects."""


class Stub:
    """One connection to a GDB stub. Use as a context manager."""

    def __init__(self, host='127.0.0.1', port=ARM9_PORT, timeout=10.0, trace=False):
        self.addr = (host, port)
        self.timeout = timeout
        self.sock = None
        self.console = []          # $O packets, decoded
        self.packet_size = 0x400   # until qSupported says otherwise
        self.noack = False
        #: Print every byte in both directions. The stub's own log is not visible from
        #: here, so when it hangs up mid-handshake this is the only way to see how far
        #: the conversation actually got.
        self.trace = trace or bool(os.environ.get('GDBSTUB_TRACE'))

    def _trace(self, arrow, data):
        if not self.trace:
            return
        try:
            text = data.decode('ascii')
        except Exception:
            text = repr(data)
        print('    %s %s' % (arrow, text), file=sys.stderr, flush=True)

    # -- connection ----------------------------------------------------

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()

    def connect(self):
        try:
            self.sock = socket.create_connection(self.addr, timeout=self.timeout)
        except (ConnectionRefusedError, socket.timeout, OSError) as exc:
            raise GdbError(NOT_LISTENING % (self.addr[0], self.addr[1], exc)) from None
        self.sock.settimeout(self.timeout)
        # **The initial ack is mandatory for melonDS.** On accepting a connection its
        # stub blocks for up to a second waiting for one byte and hangs up if none
        # arrives (GdbStub.cpp: "inital handshake: didn't receive inital ack!"). Real
        # gdb sends '+' on connect, so this is not melonDS being unusual - it is this
        # client having skipped a step. Diving straight into $qSupported makes the stub
        # eat the '$' as the ack and choke on the remainder, which presents to the user
        # as "stub closed the connection" with no explanation whatsoever.
        self._trace('->', b'+')
        self.sock.sendall(b'+')
        reply = self.cmd('qSupported:swbreak+;hwbreak+')
        for item in reply.split(';'):
            if item.startswith('PacketSize='):
                try:
                    self.packet_size = int(item[len('PacketSize='):], 16)
                except ValueError:
                    pass
        # melonDS advertises QStartNoAckMode and waits up to 2 seconds for an ack after
        # every single reply, retrying three times. Turning acks off removes that whole
        # round trip - it is both faster over a 4 MB memory search and one less thing to
        # get wrong. Only done if the stub offers it.
        if 'QStartNoAckMode+' in reply:
            if self.cmd('QStartNoAckMode') == 'OK':
                self.noack = True
        return reply

    def close(self):
        """Resume the target, then detach.

        **Resuming first is not politeness, it is required.** Detaching while the ARM9
        is halted leaves melonDS frozen, and a frozen melonDS stops servicing its own
        GDB socket - so the next connection is accepted by the OS and then never
        answered. Every "the stub wedged again" in this project's history traces back to
        a client that halted the CPU and walked away.
        """
        if self.sock:
            for packet in ('c', 'D'):
                try:
                    self.send(packet)   # fire and forget; we are leaving either way
                except Exception:
                    pass
            self.sock.close()
            self.sock = None

    def resume(self):
        """Continue without waiting for the next stop.

        `cont()` waits for a stop reply, which never comes if the game simply carries on
        running - and the timeout that follows leaves the target halted, which is the
        failure mode `close` exists to avoid.
        """
        self.send('c')

    # -- framing -------------------------------------------------------

    @staticmethod
    def _frame(payload: str) -> bytes:
        body = payload.encode('ascii')
        return b'$' + body + b'#' + ('%02x' % (sum(body) & 0xFF)).encode('ascii')

    def _recv_byte(self):
        try:
            b = self.sock.recv(1)
        except ConnectionResetError:
            raise GdbError(DROPPED % 'reset the connection') from None
        if not b:
            raise GdbError(DROPPED % 'closed the connection cleanly')
        self._trace('<-', b)
        return b

    def _read_packet(self) -> str:
        """One packet, skipping acks. Raises on a bad checksum."""
        while True:
            b = self._recv_byte()
            if b in (b'+', b'-'):
                continue
            if b == b'\x03':
                continue
            if b != b'$':
                continue
            body = bytearray()
            while True:
                ch = self._recv_byte()
                if ch == b'#':
                    break
                if ch == b'}':                      # escaped byte
                    body += bytes([self._recv_byte()[0] ^ 0x20])
                    continue
                body += ch
            want = self.sock.recv(2).decode('ascii', 'replace')
            if ('%02x' % (sum(body) & 0xFF)) != want.lower():
                if not self.noack:
                    self.sock.sendall(b'-')
                continue
            if not self.noack:
                self.sock.sendall(b'+')
            return body.decode('ascii', 'replace')

    def send(self, payload: str):
        frame = self._frame(payload)
        self._trace('->', frame)
        self.sock.sendall(frame)

    def cmd(self, payload: str, expect_stop=False) -> str:
        """Send a packet and return the first reply that is not console output."""
        self.send(payload)
        while True:
            reply = self._read_packet()
            if is_console(reply) and not expect_stop:
                self.console.append(binascii.unhexlify(reply[1:]).decode('latin1'))
                continue
            return reply

    # -- target state --------------------------------------------------

    def halt_reason(self) -> str:
        return self.cmd('?')

    def interrupt(self):
        """Ctrl-C the target; returns the stop reply."""
        self.sock.sendall(b'\x03')
        return self._read_packet()

    def registers(self):
        """[r0..r15, cpsr] as unsigned ints, or None if the stub refuses `g`."""
        raw = self.cmd('g')
        if not raw or raw.startswith('E'):
            return None
        data = binascii.unhexlify(raw[:len(raw) // 2 * 2])
        n = min(17, len(data) // 4)
        return list(struct.unpack('<%dI' % n, data[:n * 4]))

    def pc(self):
        regs = self.registers()
        return regs[15] if regs and len(regs) > 15 else None

    def read(self, addr: int, length: int) -> bytes:
        """Read target memory, split across packets the stub will accept."""
        out = bytearray()
        chunk = max(64, (self.packet_size - 32) // 2)
        while length > 0:
            n = min(chunk, length)
            reply = self.cmd('m%X,%X' % (addr, n))
            if reply.startswith('E') or not reply:
                raise GdbError('read of 0x%08X+%d failed: %r' % (addr, n, reply))
            out += binascii.unhexlify(reply)
            addr += n
            length -= n
        return bytes(out)

    def write(self, addr: int, data: bytes):
        chunk = max(32, (self.packet_size - 32) // 2)
        for i in range(0, len(data), chunk):
            part = data[i:i + chunk]
            reply = self.cmd('M%X,%X:%s' % (addr + i, len(part),
                                            binascii.hexlify(part).decode()))
            if reply != 'OK':
                raise GdbError('write to 0x%08X failed: %r' % (addr + i, reply))

    def read_u32(self, addr):
        return struct.unpack('<I', self.read(addr, 4))[0]

    def write_u32(self, addr, value):
        self.write(addr, struct.pack('<I', value & 0xFFFFFFFF))

    # -- breakpoints and watchpoints -----------------------------------

    def set_break(self, addr, kind=BP_SOFT, length=4):
        reply = self.cmd('Z%d,%X,%X' % (kind, addr, length))
        if reply != 'OK':
            raise GdbError('could not set breakpoint kind %d at 0x%08X: %r'
                           % (kind, addr, reply))

    def clear_break(self, addr, kind=BP_SOFT, length=4):
        self.cmd('z%d,%X,%X' % (kind, addr, length))

    def set_watch(self, addr, length=4, kind=WP_WRITE):
        reply = self.cmd('Z%d,%X,%X' % (kind, addr, length))
        if reply != 'OK':
            raise GdbError(
                'could not set a watchpoint at 0x%08X (kind %d): %r. melonDS does not '
                'implement every watchpoint kind; try WP_ACCESS, or fall back to a '
                'breakpoint.' % (addr, kind, reply))

    def clear_watch(self, addr, length=4, kind=WP_WRITE):
        self.cmd('z%d,%X,%X' % (kind, addr, length))

    # -- running -------------------------------------------------------

    def cont(self, timeout=None):
        """Continue, and wait for the next stop. Returns the parsed stop reply."""
        return self._resume('c', timeout)

    def step(self, timeout=None):
        return self._resume('s', timeout)

    def _resume(self, letter, timeout):
        old = self.sock.gettimeout()
        if timeout is not None:
            self.sock.settimeout(timeout)
        try:
            self.send(letter)
            while True:
                reply = self._read_packet()
                if is_console(reply):
                    self.console.append(binascii.unhexlify(reply[1:]).decode('latin1'))
                    continue
                return parse_stop(reply)
        finally:
            self.sock.settimeout(old)

    # -- searching -----------------------------------------------------

    def search(self, needle: bytes, start=MAIN_RAM[0], end=MAIN_RAM[1],
               window=0x8000, progress=None):
        """Every address in [start, end) where `needle` appears.

        Reading 4 MB over RSP is not fast - expect tens of seconds - so this reports
        progress and overlaps its windows by len(needle)-1 so a match on a boundary is
        not lost.
        """
        hits, addr = [], start
        overlap = len(needle) - 1
        while addr < end:
            n = min(window, end - addr)
            try:
                buf = self.read(addr, n)
            except GdbError:
                addr += n                      # unmapped region; skip it
                continue
            i = buf.find(needle)
            while i != -1:
                hits.append(addr + i)
                i = buf.find(needle, i + 1)
            if progress:
                progress(addr, end, len(hits))
            addr += max(1, n - overlap)
        return hits


def is_console(reply: str) -> bool:
    """Whether a packet is target console output (``$O<hex>``) rather than a reply.

    The obvious test - "starts with O" - is wrong, and wrong in a way that hangs: the
    single most common reply in the whole protocol is ``OK``, which also starts with O.
    A console packet is ``O`` followed by an **even** number of hex digits, so ``OK``
    fails on both counts. Found by the offline self-test rather than against melonDS,
    which is the entire reason that test exists.
    """
    if len(reply) < 3 or reply[0] != 'O':
        return False
    body = reply[1:]
    return len(body) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in body)


def parse_stop(reply: str) -> dict:
    """``T05watch:2001234;05:...;`` -> {'signal':5,'reason':'watch','addr':0x2001234}."""
    out = {'raw': reply, 'signal': None, 'reason': None, 'addr': None}
    if not reply:
        return out
    if reply[0] in 'STW X':
        try:
            out['signal'] = int(reply[1:3], 16)
        except ValueError:
            pass
    if reply.startswith('T'):
        for item in reply[3:].split(';'):
            if not item or ':' not in item:
                continue
            key, _, val = item.partition(':')
            if key in ('watch', 'rwatch', 'awatch'):
                out['reason'] = key
                try:
                    out['addr'] = int(val, 16)
                except ValueError:
                    pass
            elif key in ('swbreak', 'hwbreak'):
                out['reason'] = key
    return out


def probe(host='127.0.0.1', port=ARM9_PORT, trace=False):
    """Attach, report what the stub does, and leave the game running.

    Every step prints its own result. An earlier version wrapped the liveness check in a
    bare `except` and printed nothing at all when a step failed, which is how a timed-out
    memory read looked identical to a successful one that simply had nothing to say.
    """
    g = Stub(host, port, trace=trace)
    g.connect()
    try:
        print('connected to %s:%d' % (host, port))
        print('  packet size : 0x%X' % g.packet_size)
        print('  no-ack mode : %s' % ('on' if g.noack else 'off'))
        print('  halt reason : %s' % g.halt_reason())

        regs = g.registers()
        if regs is None:
            print('  registers   : the stub refused `g`')
        else:
            print('  pc          : 0x%08X %s' % (
                regs[15],
                '(main RAM - this is game code)'
                if MAIN_RAM[0] <= regs[15] < MAIN_RAM[1] else '(outside main RAM)'))
            print('  r0-r3       : %s' % ' '.join('0x%08X' % r for r in regs[:4]))

        probe_at = MAIN_RAM[0] + 0x10000
        # Step up the read size rather than going straight to a big one: "memory reads
        # work" and "memory reads work at the size the RAM search needs" are different
        # claims, and this stub has already shown it can die between one packet and the
        # next. Each size reports separately so a failure names itself.
        first = None
        for size in (16, 256, 1024):
            try:
                data = g.read(probe_at, size)
                print('  read %-6d: OK' % size)
                if first is None:
                    first = data
            except Exception as exc:
                print('  read %-6d: FAILED - %s' % (size, exc))
                print()
                print('  The stub answered the handshake and then died on a %d-byte read.'
                      % size)
                print('  Restart melonDS before trying anything else - once it stops')
                print('  answering it does not recover. If this happens every time on a')
                print('  freshly started stub, the ARM9 stub is broken in this build.')
                return

        # Single-step first. Attaching **halts the ARM9 by design** - melonDS sets
        # `stay = true` on a new connection and holds the core until told to continue -
        # so "the PC is not moving" is the expected state here, not a symptom. Stepping
        # separates the two things that look alike: whether the CPU can execute at all,
        # and whether the continue packet is being honoured.
        pc_step = g.pc()
        stepped = []
        for _ in range(3):
            try:
                g.step(timeout=4)
                stepped.append(g.pc())
            except Exception as exc:
                print('  single-step : FAILED - %s' % exc)
                break
        if stepped:
            print('  single-step : pc %s' % ' -> '.join('0x%08X' % p for p in
                                                        [pc_step] + stepped))
            print('                %s' % ('CPU executes' if len(set(stepped)) > 1
                                          or stepped[0] != pc_step
                                          else 'PC never changed - CPU is not executing'))

        # Liveness: let it run for a second and see whether anything moved. A halted or
        # hung emulator changes neither the PC nor RAM; a running game changes both.
        pc_before = regs[15] if regs else None
        g.resume()
        time.sleep(1.0)
        try:
            g.interrupt()
            pc_after = g.pc()
            second = g.read(probe_at, len(first))
        except Exception as exc:
            print('  liveness    : could not re-halt after resuming - %s' % exc)
            return
        moved = (pc_before != pc_after) or (first != second)
        print('  liveness    : %s' % ('RUNNING' if moved else 'NOT RUNNING'))
        print('                pc 0x%08X -> 0x%08X, sampled RAM %s'
              % (pc_before or 0, pc_after or 0,
                 'changed' if first != second else 'identical'))
        if not moved:
            # Worth spelling out, because the protocol side looks identical either way:
            # the stub answered every packet, so this is the emulated CPU standing still,
            # not a debugging problem.
            print()
            print('  The stub answered everything, so this is not a protocol problem -')
            print('  the emulated ARM9 is simply not getting anywhere. For this game the')
            print('  overwhelmingly likely cause is the known melonDS tutorial freeze:')
            print('  if the save did not load, the game is stuck in the opening tutorial')
            print('  and the CPU is spinning at one address. Check the melonDS window.')
            print()
            print('  Also possible: emulation paused in melonDS (System menu), or no ROM')
            print('  loaded. A watchpoint experiment needs the game actually playing.')
        if g.console:
            print('  console     : %s' % ''.join(g.console)[-200:])
    finally:
        # Always hand the game back running, whatever happened above.
        g.close()
        print('  detached, target resumed')


def resume_target(host='127.0.0.1', port=ARM9_PORT):
    """Unfreeze a target left halted by an earlier run, without restarting melonDS."""
    g = Stub(host, port)
    g.connect()
    g.close()
    print('sent continue + detach to %s:%d - melonDS should be running again' % (host, port))


def main():
    try:
        _main()
    except GdbError as exc:
        print(file=sys.stderr)
        print(exc, file=sys.stderr)
        sys.exit(1)


def _main():
    args = sys.argv[1:]
    trace = '--trace' in args
    args = [a for a in args if a != '--trace']
    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        print('usage:\n'
              '  py gdbstub.py probe [port] [--trace]\n'
              '  py gdbstub.py resume [port]   # unfreeze a halted target\n'
              '  py gdbstub.py read <hex addr> <len>\n'
              '  py gdbstub.py search <hex bytes>\n')
        return
    if args[0] == 'probe':
        probe(port=int(args[1]) if len(args) > 1 else ARM9_PORT, trace=trace)
    elif args[0] == 'resume':
        resume_target(port=int(args[1]) if len(args) > 1 else ARM9_PORT)
    elif args[0] == 'read':
        with Stub() as g:
            data = g.read(int(args[1], 16), int(args[2], 0))
            for i in range(0, len(data), 16):
                row = data[i:i + 16]
                print('%08X  %-47s  %s'
                      % (int(args[1], 16) + i,
                         ' '.join('%02X' % x for x in row),
                         ''.join(chr(c) if 32 <= c < 127 else '.' for c in row)))
    elif args[0] == 'search':
        needle = binascii.unhexlify(args[1])
        with Stub() as g:
            hits = g.search(needle, progress=lambda a, e, n: print(
                '\r  0x%08X (%d hits)' % (a, n), end='', file=sys.stderr))
            print('\n%d hit(s): %s' % (len(hits), ' '.join('0x%08X' % h for h in hits)))
    else:
        print('unknown command %r' % args[0])


if __name__ == '__main__':
    main()
