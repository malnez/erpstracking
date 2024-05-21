import serial
import socket
from datetime import datetime, timezone, timedelta
import threading

def calculate_checksum(sentence):
    """
    Calculate the checksum of a NMEA 0183 sentence.
    """
    checksum = 0
    for char in sentence:
        checksum ^= ord(char)
    checksum_hex = "{:02X}".format(checksum)
    return checksum_hex

def wpl_to_gga(wpl_data, station_id):
    wpl_parts = wpl_data.split(',')
    if len(wpl_parts) < 6:
        return None

    lat = float(wpl_parts[1])
    lat_direction = wpl_parts[2]
    lon = float(wpl_parts[3])
    lon_direction = wpl_parts[4]

    if lat_direction == 'S':
        lat = -lat
    if lon_direction == 'W':
        lon = -lon

    latitude = f"{abs(lat):08.4f}"
    longitude = f"{abs(lon):09.4f}"

    utc_time = datetime.now(timezone.utc).strftime('%H%M%S.00')

    gga_sentence = f"{utc_time},{latitude},{lat_direction},{longitude},{lon_direction},1,12,0.5,0.0,M,0.0,M,1.0,{station_id}"
    checksum = calculate_checksum(f"GPGGA,{gga_sentence}")
    return f"$GPGGA,{gga_sentence}*{checksum}\r\n"

def handle_client(client_socket, station_name):
    while True:
        try:
            data = client_socket.recv(1024)
            if not data:
                break
            print(f"Received from {station_name}: {data.decode('utf-8').strip()}")
        except Exception as e:
            print(f"Error handling client {station_name}: {e}")
            break

def listen_wpl_and_broadcast(ser, stations):
    while True:
        line = ser.readline().decode('utf-8').strip()
        if line.startswith('$GPWPL'):
            print(f"Original GPWPL sentence: {line}")
            for station_name, station_info in stations.items():
                if station_name in line:
                    gga_sentence = wpl_to_gga(line, station_info["id"])
                    if gga_sentence:
                        print(f"GGA sentence for {station_name}: {gga_sentence.strip()}")
                        try:
                            station_info["client_socket"].sendall(gga_sentence.encode())
                        except Exception as e:
                            print(f"Error broadcasting to {station_name}: {e}")

def main():
    ser = serial.Serial('COM7', 9600, timeout=1)
    base_port = 1234
    stations = {}
    station_counter = 1

    expected_stations = int(input("Enter the number of expected stations: "))
    print(f"Listening for GPWPL sentences to define up to {expected_stations} stations...")

    # Start time for collecting station names
    start_time = datetime.now()

    # Collect station names until the expected number of stations are defined or until 3 minutes have passed
    while (datetime.now() - start_time) < timedelta(minutes=3):
        if len(stations) >= expected_stations:
            break

        line = ser.readline().decode('utf-8').strip()
        if line.startswith('$GPWPL'):
            print(f"Original GPWPL sentence: {line}")
            wpl_parts = line.split(',')
            if len(wpl_parts) >= 6:
                station_name = wpl_parts[5].split('*')[0]  # Extract station name without checksum part
                if station_name not in stations:
                    station_id = f"{station_counter:04d}"
                    port = base_port + station_counter - 1
                    station_counter += 1
                    stations[station_name] = {"id": station_id, "port": port, "socket": None, "client_socket": None}
                    print(f"Station {station_name} defined with ID {station_id} and port {port}")

    print("Finished collecting station names. Now setting up server sockets and waiting for connections...")

    # Create and bind server sockets for each station
    for station_name, station_info in stations.items():
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind(('localhost', station_info["port"]))
        server_socket.listen(1)
        station_info["socket"] = server_socket
        print(f"TCP server listening on localhost:{station_info['port']} for station {station_name}")

    # Wait for connections on each port
    for station_name, station_info in stations.items():
        client_socket, addr = station_info["socket"].accept()
        station_info["client_socket"] = client_socket
        print(f"Connection established with client for station {station_name} on {addr}")

        # Start a thread to handle client communication
        threading.Thread(target=handle_client, args=(client_socket, station_name)).start()

    # Start a thread to listen for WPL sentences and broadcast them as GGA sentences
    threading.Thread(target=listen_wpl_and_broadcast, args=(ser, stations)).start()

if __name__ == "__main__":
    main()
