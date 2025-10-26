from socket import *
from protocol import unpack_packet, pack_packet, FLAG_DATA

SERVER_NAME = 'localhost'
SERVER_PORT = 12000

def main():
    
  clientSocket = socket(AF_INET, SOCK_DGRAM)
  serverAddress = (SERVER_NAME, SERVER_PORT)

  sequence_number = 1
  window_size = 10

  message = input('Input lowercase sentence: ').encode()

  packageClient = pack_packet(
      version=1,
      flags=FLAG_DATA,
      seq=sequence_number,
      ack=0,
      win=window_size,
      payload=message
  )

  clientSocket.sendto(packageClient, serverAddress)


  datagram, addr = clientSocket.recvfrom(2048)
  packageServer = unpack_packet(datagram)

  print("checksum_ok:", packageServer["checksum_ok"])
  print("ack recebido:", packageServer["ack"])
  print("resposta:", packageServer["payload"].decode(errors="ignore"))

  clientSocket.close()

if __name__ == "__main__":
    main()


