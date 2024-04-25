import serial
import socket
from datetime import datetime, timezone


def calculate_checksum(sentence):
    """
    Calculate the checksum of a NMEA 0183 sentence
    """
    checksum = 0
    for char in sentence:
        checksum ^= ord(char)
    checksum_hex = "{:02X}".format(checksum)
    return checksum_hex


def wpl_to_gga(wpl_data):
    wpl_parts = wpl_data.split(',')
    if len(wpl_parts) < 6:
        return None

    station_name = wpl_parts[5]
    if "Mark test" in station_name:
        station_id = '0001'
    elif "Baza T3S3" in station_name:
        station_id = '0002'
    else:
        station_id = '0000'  # Default station ID

    lat = float(wpl_parts[1])
    lat_direction = wpl_parts[2]
    lon = float(wpl_parts[3])
    lon_direction = wpl_parts[4]

    if lat_direction == 'S':
        lat = -lat
    if lon_direction == 'W':
        lon = -lon

    latitude = f"{lat:.4f}"
    longitude = f"{lon:.4f}"

    utc_time = datetime.now(timezone.utc).strftime('%H%M%S.00')

    gga_sentence = f"{utc_time},{latitude},{lat_direction},{longitude},{lon_direction},1,12,0.5,0.0,M,0.0,M,1.0,{station_id}"
    checksum = calculate_checksum(f"GPGGA,{gga_sentence}")
    return f"$GPGGA,{gga_sentence}*{checksum}\r\n"


def main():
    ser = serial.Serial('COM5', 9600, timeout=1)

    # Create TCP server sockets for stations 0001 and 0002
    server_socket_0001 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket_0001.bind(('localhost', 1234))
    server_socket_0001.listen(1)  # Allow 1 client to connect for station 0001
    print("TCP server listening on localhost:1234 for station 0001")

    server_socket_0002 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket_0002.bind(('localhost', 1235))
    server_socket_0002.listen(1)  # Allow 1 client to connect for station 0002
    print("TCP server listening on localhost:1235 for station 0002")

    while True:
        # Accept connections for station 0001
        client_socket_0001, addr_0001 = server_socket_0001.accept()
        print(f"Connection established with client for station 0001 on {addr_0001}")

        # Accept connections for station 0002
        client_socket_0002, addr_0002 = server_socket_0002.accept()
        print(f"Connection established with client for station 0002 on {addr_0002}")

        while True:
            line = ser.readline().decode('utf-8').strip()
            if line.startswith('$GPWPL'):
                print("Original GPWPL sentence:", line)
                gga_sentence = wpl_to_gga(line)
                if gga_sentence:
                    print("GGA sentence:", gga_sentence)
                    try:
                        if "Mark test" in line:
                            client_socket_0001.sendall(gga_sentence.encode())
                            print("GGA Sentence sent to client for station 0001")
                        elif "Baza T3S3" in line:
                            client_socket_0002.sendall(gga_sentence.encode())
                            print("GGA Sentence sent to client for station 0002")
                    except Exception as e:
                        print("Error broadcasting:", e)
            elif line.startswith('$GPGGA'):
                print("GGA sentence:", line)

if __name__ == "__main__":
    main()
