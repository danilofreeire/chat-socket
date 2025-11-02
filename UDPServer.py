from socket import *
from protocol import unpack_packet, pack_packet, FLAG_DATA, FLAG_ACK
import time

SERVER_PORT = 12000
RECV_CAPACITY = 10  # capacidade máxima de "buffer" do servidor (em pacotes)


def main():
    serverSocket = socket(AF_INET, SOCK_DGRAM)
    serverSocket.bind(("", SERVER_PORT))
    print(f"Server pronto em {SERVER_PORT} \n")

    # ── Tabelas de estado ───────────────────────────────────────────────
    clients = {}  # (ip, porta): timestamp do último pacote
    expectedNumberSequence = {}  # próximo número de sequência esperado por cliente
    lastAck = {}  # último ACK cumulativo enviado por cliente
    recvBufferUsage = {}  # simula ocupação de buffer (para controle de fluxo)
    usernames = {}  # (ip, porta): nome do usuário

    try:
        while True:
            try:
                datagram, clientAddress = serverSocket.recvfrom(2048)
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
            expectedNumber = expectedNumberSequence[clientAddress]

            print(
                f"[{clientAddress}] seq={sequenceNumber} esperado={expectedNumber} ok={checksumOk}"
            )

            # Simula "espaço livre" no buffer para controle de fluxo
            used = recvBufferUsage.get(clientAddress, 0)
            free = max(RECV_CAPACITY - used, 0)  # janela anunciada (win)
            if free == 0:
                print(f"🚫 Buffer cheio, anunciando win=0 para {clientAddress}")

            # ── Pacote correto e em ordem ─────────────────────────────
            if checksumOk and (flags & FLAG_DATA) and sequenceNumber == expectedNumber:
                try:
                    raw_text = packageClient["payload"].decode(errors="ignore")

                    # se ainda não conhecemos o nome deste cliente → primeira msg é o username
                    if clientAddress not in usernames:
                        usernames[clientAddress] = (
                            raw_text.strip() or f"{clientAddress[0]}:{clientAddress[1]}"
                        )

                        # atualiza estado
                        lastAck[clientAddress] = sequenceNumber
                        expectedNumberSequence[clientAddress] = expectedNumber + 1

                        # envia apenas ACK (não encaminha)
                        ack_only = pack_packet(
                            version=1,
                            flags=FLAG_ACK,
                            seq=0,
                            ack=lastAck[clientAddress],
                            window_size=free,
                            payload=b"",
                        )
                        serverSocket.sendto(ack_only, clientAddress)
                        print(
                            f"👤 Username registrado: {usernames[clientAddress]} para {clientAddress}"
                        )
                        continue

                    # a partir daqui são mensagens normais
                    sender_name = usernames.get(
                        clientAddress, f"{clientAddress[0]}:{clientAddress[1]}"
                    )
                    forwarded_text = f"{sender_name} > {raw_text}"
                    data_to_send = forwarded_text.encode()

                    recvBufferUsage[clientAddress] = min(RECV_CAPACITY, used + 1)

                    # atualiza estado
                    lastAck[clientAddress] = sequenceNumber
                    expectedNumberSequence[clientAddress] = expectedNumber + 1

                    # envia ACK para o remetente
                    ack_pkt = pack_packet(
                        version=1,
                        flags=FLAG_ACK,
                        seq=0,
                        ack=lastAck[clientAddress],
                        window_size=free,
                        payload=b"",
                    )
                    serverSocket.sendto(ack_pkt, clientAddress)
                    print(
                        f"⏩ ACK enviado ao remetente {clientAddress} (ack={lastAck[clientAddress]})"
                    )

                    # escolhe destinatário
                    other = next(
                        (c for c in clients.keys() if c != clientAddress), None
                    )
                    if other:
                        fwd_pkt = pack_packet(
                            version=1,
                            flags=FLAG_DATA,
                            seq=0,
                            ack=0,
                            window_size=free,
                            payload=data_to_send,
                        )
                        serverSocket.sendto(fwd_pkt, other)
                        print(f"📤 Mensagem encaminhada para {other}")
                    else:
                        # nenhum outro cliente — responde informando
                        info = "Nenhum outro cliente conectado ainda; sua mensagem nao foi encaminhada."
                        info_pkt = pack_packet(
                            version=1,
                            flags=FLAG_DATA | FLAG_ACK,
                            seq=0,
                            ack=lastAck[clientAddress],
                            window_size=free,
                            payload=f"[servidor] {info}".encode(),
                        )
                        serverSocket.sendto(info_pkt, clientAddress)
                        print(
                            "ℹ️  Nenhum destinatario disponivel; informei o remetente."
                        )

                    # libera buffer simulado
                    if recvBufferUsage[clientAddress] > 0:
                        recvBufferUsage[clientAddress] -= 1

                except Exception as e:
                    print("Descartando pacote inválido:", e)
                    continue

            # ── Pacote duplicado, fora de ordem ou com erro ────────────────
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
        print("\n🛑 Interrompido pelo usuário (Ctrl+C). Fechando socket...")
    finally:
        serverSocket.close()


if __name__ == "__main__":
    main()
