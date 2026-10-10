"""
Offline self-test for `gdbstub.py`: a fake GDB stub, so the protocol is proven without
melonDS, without the game, and without anyone sitting at an emulator.

This is the only test in the project that is not the build pipeline checking itself, and
it earned its place immediately. The first run found a hang that would have happened
against the real stub: the client treated the reply `OK` as a console-output packet,
because `$O<hex>` console output also starts with `O`. A bug that only shows up when the
target is halted at a watchpoint is a bug nobody wants to debug through an emulator.

    py tools/recon/gdbstub_selftest.py      # exits non-zero on failure
"""

import binascii, socket, struct, sys, threading
sys.path.insert(0, 'tools/recon')
import gdbstub

RAM_BASE = 0x02000000
RAM = bytearray(0x20000)
struct.pack_into('<I', RAM, 0x1000, 0xDEADBEEF)
RAM[0x2000:0x2008] = b'SONICCHR'

def checksum(b): return '%02x' % (sum(b) & 0xFF)

def serve(conn):
    buf = b''
    regs = [0]*17
    regs[15] = 0x0203ABCD
    regs[0] = 0x11223344
    stage = {'n': 0}
    while True:
        data = conn.recv(4096)
        if not data: return
        buf += data
        while b'$' in buf and b'#' in buf:
            s = buf.index(b'$'); e = buf.index(b'#', s)
            if len(buf) < e + 3: break
            payload = buf[s+1:e]; buf = buf[e+3:]
            conn.sendall(b'+')
            p = payload.decode()
            if p.startswith('qSupported'):
                r = 'PacketSize=1000;swbreak+;hwbreak+'
            elif p == '?':
                r = 'S05'
            elif p == 'g':
                r = binascii.hexlify(struct.pack('<17I', *regs)).decode()
            elif p.startswith('m'):
                a, n = p[1:].split(',')
                a = int(a, 16) - RAM_BASE; n = int(n, 16)
                r = (binascii.hexlify(bytes(RAM[a:a+n])).decode()
                     if 0 <= a and a + n <= len(RAM) else 'E01')
            elif p.startswith('M'):
                head, hexdata = p[1:].split(':')
                a, n = head.split(','); a = int(a,16) - RAM_BASE
                RAM[a:a+int(n,16)] = binascii.unhexlify(hexdata)
                r = 'OK'
            elif p.startswith('Z') or p.startswith('z'):
                r = 'OK'
            elif p == 'c':
                stage['n'] += 1
                r = 'T05watch:02001000;0f:cdab0302;'
            elif p == 's':
                r = 'T05'
            elif p == 'D':
                r = 'OK'
            else:
                r = ''
            body = r.encode()
            conn.sendall(b'$' + body + b'#' + checksum(body).encode())

srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('127.0.0.1', 3399)); srv.listen(1)
def run():
    try:
        serve(srv.accept()[0])
    except Exception as e:
        import traceback; traceback.print_exc()
threading.Thread(target=run, daemon=True).start()

ok = True
with gdbstub.Stub(port=3399) as g:
    print('packet size 0x%X' % g.packet_size); ok &= g.packet_size == 0x1000
    print('halt        %s' % g.halt_reason())
    r = g.registers(); print('pc          0x%08X' % r[15]); ok &= r[15] == 0x0203ABCD
    v = g.read_u32(RAM_BASE + 0x1000); print('read_u32    0x%08X' % v); ok &= v == 0xDEADBEEF
    g.write_u32(RAM_BASE + 0x1000, 0xCAFEBABE)
    v = g.read_u32(RAM_BASE + 0x1000); print('after write 0x%08X' % v); ok &= v == 0xCAFEBABE
    big = g.read(RAM_BASE, 0x1800); print('chunked read %d bytes' % len(big)); ok &= len(big) == 0x1800
    hits = g.search(b'SONICCHR', RAM_BASE, RAM_BASE + len(RAM))
    print('search      %s' % [hex(h) for h in hits]); ok &= hits == [RAM_BASE + 0x2000]
    stop = g.cont(timeout=5)
    print('stop        %s' % {k: (hex(v) if isinstance(v,int) else v) for k,v in stop.items()})
    ok &= stop['reason'] == 'watch' and stop['addr'] == 0x02001000 and stop['signal'] == 5
print('\nSELF-TEST', 'PASSED' if ok else 'FAILED')
sys.exit(0 if ok else 1)
