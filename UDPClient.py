from socket import *
from protocol import unpack_packet, pack_packet, FLAG_DATA
import time

SERVER_NAME = 'localhost'
SERVER_PORT = 12000
WINDOW_SIZE = 5
TIMEOUT= 10


def main():
  clientSocket = socket(AF_INET, SOCK_DGRAM)
  serverAddress = (SERVER_NAME, SERVER_PORT)

  # timeout curto no socket para checar timer com frequência
  clientSocket.settimeout(0.05)  # 50ms

  # estado
  base = 1
  nextSequenceNumber = 1
  packages = {}

  # timer lógico do pacote 'base'
  timer_start = None  # None = parado; caso contrário guarda time.monotonic()


  print("Digite /quit para sair.  ")
  while True:
      
    message = input('Input lowercase sentence: ').encode()
    if not message:
        continue 
    if message.decode().strip() == '/quit':
        break


    # ===== ENVIO =====
    if(nextSequenceNumber < base + WINDOW_SIZE):
      sequence_number = nextSequenceNumber # número de sequência do pacote atual

      packageClient = pack_packet(
        version=1,
        flags=FLAG_DATA,
        seq=sequence_number,
        ack=0,
        window_size=WINDOW_SIZE,
        payload=message
      )
      packages[sequence_number] = packageClient
      clientSocket.sendto(packageClient, serverAddress)
            
      #se for o primeiro da janela, inicia/reinicia o timer lógico
      if(base == nextSequenceNumber):
        timer_start = time.monotonic()
      nextSequenceNumber += 1

    else:
      print("Janela cheia, aguardando...")
    
    try:  
      datagram, addr = clientSocket.recvfrom(2048)
      packageServer = unpack_packet(datagram)

      ackNumberServer = packageServer.get("ack", None)

      if ackNumberServer is not None:
        base = ackNumberServer + 1
        # se esvaziou a janela, para; senão, reinicia o timer pro novo base
        if base == nextSequenceNumber:
          timer_start = None  # para o timer lógico
        else:
          timer_start = time.monotonic()  # reinicia o timer lógico

    except timeout:
        pass  # sem ACK agora, segue pra checar o timer



    # CHECAGEM DO TIMER (Go-Back-N)
    if timer_start is not None and (time.monotonic() - timer_start) >= TIMEOUT:
        # estourou: retransmite de base até o último enviado
        for sequence_number in range(base, next_seq_num):
            clientSocket.sendto(packages[sequence_number], serverAddress)
        # reinicia o timer do (novo) base
        timer_start = time.monotonic()
      




    # print("checksum_ok:", packageServer["checksum_ok"])
    # print("ack recebido:", packageServer["ack"])
    print("resposta:", packageServer["payload"].decode(errors="ignore"))
    sequence_number += 1

  clientSocket.close()

if __name__ == "__main__":
    main()


