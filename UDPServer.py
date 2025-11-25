from socket import *
from protocol import unpack_packet, pack_packet, FLAG_DATA, FLAG_ACK
import time

SERVER_PORT = 12000
RECV_CAPACITY = 10
TIMEOUT = 4.0  # Tempo para o servidor retransmitir


def main():
    serverSocket = socket(AF_INET, SOCK_DGRAM)
    serverSocket.bind(("", SERVER_PORT))
    serverSocket.settimeout(0.5)  # Necessário para checar retransmissão periodicamente
    print(f"Server pronto em {SERVER_PORT} \n")

    # ── Tabelas de estado ───────────────────────────────────────────────
    clients = {}  # (ip, porta): timestamp do último pacote
    expectedNumberSequence = {}  # Próximo SEQ esperado DO cliente (Recebimento)
    lastAck = {}  # Último ACK enviado AO cliente
    recvBufferUsage = {}  # Controle de fluxo
    usernames = {}  # Nome do usuário

    # [NOVO] Estruturas para retransmissão do Servidor -> Cliente
    # { (ip, porta): { seq: {'pkt': bytes, 'time': float} } }
    forward_buffer = {}
    # { (ip, porta): int } -> Próximo SEQ a enviar PARA o cliente
    server_seq_out = {}

    try:
        while True:
            try:
                datagram, clientAddress = serverSocket.recvfrom(2048)
            except timeout:
                # [NOVO] Verifica timeouts de retransmissão do servidor
                now = time.time()
                for dest_addr, buffer in forward_buffer.items():
                    for seq_num, item in list(buffer.items()):
                        if now - item["time"] >= TIMEOUT:
                            print(
                                f"⏳ [SERVER] Timeout p/ {dest_addr} seq={seq_num}. Retransmitindo..."
                            )
                            try:
                                serverSocket.sendto(item["pkt"], dest_addr)
                                item["time"] = now  # Reinicia timer
                            except Exception as e:
                                print(f"Erro retransmissão server: {e}")
                continue
            except Exception as e:
                print("Erro ao receber pacote:", e)
                continue

            # registra cliente
            first_time = clientAddress not in clients
            clients[clientAddress] = time.time()

            if first_time:
                expectedNumberSequence[clientAddress] = 1
                lastAck[clientAddress] = 0
                recvBufferUsage[clientAddress] = 0
                forward_buffer[clientAddress] = {}
                server_seq_out[clientAddress] = 1
                print(f"[NOVO CLIENTE] {clientAddress} (total={len(clients)})")
                print(f"Clientes atuais: {list(clients.keys())}\n")

            # tenta desempacotar
            try:
                packageClient = unpack_packet(datagram)
            except Exception as e:
                print(f"[{clientAddress}] pacote inválido: {e}")
                continue

            sequenceNumber = packageClient["seq"]
            checksumOk = packageClient["checksum_ok"]
            flags = packageClient["flags"]

            # [NOVO] Tratamento de ACKs puros vindos do Cliente (Confirmação de msg encaminhada)
            # Se for apenas ACK (sem dados), removemos do buffer de retransmissão
            if checksumOk and (flags & FLAG_ACK) and not (flags & FLAG_DATA):
                ack_rec = packageClient["ack"]
                if (
                    clientAddress in forward_buffer
                    and ack_rec in forward_buffer[clientAddress]
                ):
                    del forward_buffer[clientAddress][ack_rec]
                    print(
                        f"✅ [SERVER] ACK {ack_rec} recebido de {clientAddress}. Retirado do buffer."
                    )
                continue

            # Processamento normal de DADOS
            expectedNumber = expectedNumberSequence[clientAddress]
            print(
                f"[{clientAddress}] seq={sequenceNumber} esperado={expectedNumber} ok={checksumOk}"
            )

            used = recvBufferUsage.get(clientAddress, 0)
            free = max(RECV_CAPACITY - used, 0)
            if free == 0:
                print(f"🚫 Buffer cheio, anunciando win=0 para {clientAddress}")

            # ── Pacote correto e em ordem ─────────────────────────────
            if checksumOk and (flags & FLAG_DATA) and sequenceNumber == expectedNumber:
                try:
                    raw_text = packageClient["payload"].decode(errors="ignore")

                    # Login / Username
                    if clientAddress not in usernames:
                        usernames[clientAddress] = (
                            raw_text.strip() or f"{clientAddress[0]}:{clientAddress[1]}"
                        )
                        lastAck[clientAddress] = sequenceNumber
                        expectedNumberSequence[clientAddress] = expectedNumber + 1

                        # ACK do login
                        ack_only = pack_packet(
                            version=1,
                            flags=FLAG_ACK,
                            seq=0,
                            ack=lastAck[clientAddress],
                            window_size=free,
                            payload=b"",
                        )
                        serverSocket.sendto(ack_only, clientAddress)
                        print(f"👤 Username registrado: {usernames[clientAddress]}")
                        continue

                    # Mensagem normal (Encaminhamento)
                    # a partir daqui são mensagens normais
                    sender_name = usernames.get(
                        clientAddress, f"{clientAddress[0]}:{clientAddress[1]}"
                    )

                    # CORREÇÃO: Usar '|' como separador para a GUI do cliente entender
                    # Antes era: forwarded_text = f"{sender_name} > {raw_text}"
                    forwarded_text = f"{sender_name}|{raw_text}"

                    data_to_send = forwarded_text.encode()

                    recvBufferUsage[clientAddress] = min(RECV_CAPACITY, used + 1)

                    # Atualiza estado (Recebimento)
                    lastAck[clientAddress] = sequenceNumber
                    expectedNumberSequence[clientAddress] = expectedNumber + 1

                    # Envia ACK para o REMETENTE (Confirmando que o server recebeu)
                    ack_pkt = pack_packet(
                        version=1,
                        flags=FLAG_ACK,
                        seq=0,
                        ack=lastAck[clientAddress],
                        window_size=free,
                        payload=b"",
                    )
                    serverSocket.sendto(ack_pkt, clientAddress)
                    print(f"⏩ ACK enviado ao remetente {clientAddress}")

                    # Escolhe destinatário e ENCAMINHA
                    other = next(
                        (c for c in clients.keys() if c != clientAddress), None
                    )
                    if other:
                        # [NOVO] Lógica de envio confiável para o DESTINATÁRIO
                        seq_out = server_seq_out.get(other, 1)

                        fwd_pkt = pack_packet(
                            version=1,
                            flags=FLAG_DATA,
                            seq=seq_out,  # Usa sequencial real
                            ack=0,
                            window_size=free,
                            payload=data_to_send,
                        )

                        # Guarda no buffer para retransmitir se necessário
                        if other not in forward_buffer:
                            forward_buffer[other] = {}
                        forward_buffer[other][seq_out] = {
                            "pkt": fwd_pkt,
                            "time": time.time(),
                        }
                        server_seq_out[other] = seq_out + 1

                        serverSocket.sendto(fwd_pkt, other)
                        print(f"📤 Mensagem encaminhada para {other} (seq={seq_out})")
                    else:
                        # Nenhum destinatário (não precisa salvar no buffer pois é aviso do sistema)
                        info = "Nenhum outro cliente conectado ainda."
                        info_pkt = pack_packet(
                            version=1,
                            flags=FLAG_DATA | FLAG_ACK,
                            seq=0,
                            ack=lastAck[clientAddress],
                            window_size=free,
                            payload=f"[servidor] {info}".encode(),
                        )
                        serverSocket.sendto(info_pkt, clientAddress)
                        print("ℹ️  Nenhum destinatario disponivel.")

                    if recvBufferUsage[clientAddress] > 0:
                        recvBufferUsage[clientAddress] -= 1

                except Exception as e:
                    print("Descartando pacote inválido:", e)
                    continue

            # ── Pacote duplicado ou erro ────────────────
            else:
                dupAckNumber = lastAck.get(clientAddress, 0)
                packageServer = pack_packet(
                    version=1,
                    flags=FLAG_ACK,
                    seq=0,
                    ack=dupAckNumber,
                    window_size=free,
                    payload=b"",
                )
                serverSocket.sendto(packageServer, clientAddress)
                print(f"↩️  DUP-ACK reenviado ({dupAckNumber})")

    except KeyboardInterrupt:
        print("\n🛑 Interrompido pelo usuário.")
    finally:
        serverSocket.close()


if __name__ == "__main__":
    main()
