from socket import *
from protocol import unpack_packet, pack_packet, FLAG_DATA
import time

SERVER_PORT = 12000

def main():
    serverSocket = socket(AF_INET, SOCK_DGRAM)
    serverSocket.bind(('',SERVER_PORT))
    print(f"Server pronto em {SERVER_PORT} \n")

    # ── Tabela de clientes vistos: { (ip, porta): last_seen_epoch }
    clients = {}

    while True:
        datagram, clientAddress = serverSocket.recvfrom(2048)

        # ── registra/atualiza quem enviou este datagrama
        first_time = clientAddress not in clients
        clients[clientAddress] = time.time()
        
        if first_time:
            print(f"[NOVO CLIENTE] {clientAddress} (total={len(clients)})")
            # opcional: listar todos
            print(f"Clientes atuais:  {list(clients.keys())} \n")


        try:
            packageClient = unpack_packet(datagram)
        except Exception as e:
            print("Descartando pacote inválido:", e)
            continue

        #print(f"[{clientAddress}] seq={packageClient['seq']} len={packageClient['len']} cksum_ok={packageClient['checksum_ok']}")
        
        if not packageClient["checksum_ok"]:
            # Só para teste simples: ignore se corrompido
            continue

        data = packageClient["payload"].decode(errors="ignore").upper().encode()

        packageServer = pack_packet(
            version=1,
            flags=FLAG_DATA,
            seq=0,
            ack=packageClient["seq"] + 1,
            win=10,
            payload=data
        )


        serverSocket.sendto(packageServer, clientAddress)

if __name__ == "__main__":
    main()