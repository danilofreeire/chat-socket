# protocol.py
# Cabeçalho da camada de aplicação (nosso “mini TCP” sobre UDP)
# Layout (big-endian, 18 bytes fixos):
# | version:1 | flags:1 | seq:4 | ack:4 | win:2 | len:2 | checksum:2 | + payload(len) |

from __future__ import annotations
import struct

# Formatos binários (big-endian / network order)
_HDR_NO_CSUM = ">BBIIHH"   # version, flags, seq, ack, win, len
_HDR_FULL    = ">BBIIHHH"  # + checksum (H)
HEADER_SIZE  = struct.calcsize(_HDR_FULL)  # 18 bytes

# Flags (bitmask)
FLAG_DATA          = 0x01  # 0000 0001 → pacote contém dados
FLAG_ACK           = 0x02  # 0000 0010 → pacote é ACK
FLAG_TEST_DROP_PKT = 0x04  # 0000 0100 → modo de teste: descartar pacotes
FLAG_TEST_DROP_ACK = 0x08  # 0000 1000 → modo de teste: descartar ACKs
FLAG_TEST_ERR      = 0x10  # 0001 0000 → modo de teste: corromper pacote

def internet_checksum(data: bytes) -> int:
    """Internet checksum 16-bit (one's complement) sobre data."""
    # padding se tamanho ímpar
    if len(data) & 1:
        data += b"\x00"
    s = 0
    for i in range(0, len(data), 2):
        w = (data[i] << 8) | data[i + 1]
        s = (s + w) & 0xFFFF
    return (~s) & 0xFFFF

def pack_packet(
    *,
    version: int,
    flags: int,
    seq: int,
    ack: int,
    win: int,
    payload: bytes,
) -> bytes:
    """
    Monta (header+payload) com checksum calculado.
    - len é derivado automaticamente do payload.
    - checksum é calculado sobre (header com checksum=0) + payload.
    """
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload deve ser bytes/bytearray")

    length = len(payload)

    # 1) header sem checksum
    header_no_csum = struct.pack(_HDR_NO_CSUM, version, flags, seq, ack, win, length)

    # 2) checksum sobre header(sem csum) + payload
    csum = internet_checksum(header_no_csum + payload)

    # 3) header completo
    header_full = struct.pack(_HDR_FULL, version, flags, seq, ack, win, length, csum)

    # 4) modo de teste: corromper propositalmente (se FLAG_TEST_ERR setada)
    if flags & FLAG_TEST_ERR and length > 0:
        # flip de um bit no primeiro byte do payload (simples e visível)
        corrupted = bytearray(payload)
        corrupted[0] ^= 0x01
        payload = bytes(corrupted)

    return header_full + payload

def unpack_packet(datagram: bytes) -> dict:
    """
    Lê (header+payload) e retorna um dict com campos e validação do checksum.
    Lança ValueError se o datagrama for curto ou 'len' não bater.
    """
    if len(datagram) < HEADER_SIZE:
        raise ValueError("datagrama menor que o tamanho do cabeçalho")

    version, flags, seq, ack, win, length, csum = struct.unpack(
        _HDR_FULL, datagram[:HEADER_SIZE]
    )
    payload = datagram[HEADER_SIZE:]

    if len(payload) != length:
        raise ValueError(f"LEN={length} não bate com bytes de payload={len(payload)}")

    # Recalcular checksum como recebido (sem alterar nada):
    header_no_csum = struct.pack(_HDR_NO_CSUM, version, flags, seq, ack, win, length)
    expected = internet_checksum(header_no_csum + payload)
    checksum_ok = (expected == csum)

    return {
        "version": version,
        "flags": flags,
        "seq": seq,
        "ack": ack,
        "win": win,
        "len": length,
        "checksum": csum,
        "checksum_ok": checksum_ok,
        "payload": payload,
    }
