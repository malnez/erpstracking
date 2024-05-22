import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import serial.tools.list_ports
import threading
import serial
import socket
from datetime import datetime, timezone, timedelta

stop_event = threading.Event()
stations = {}

def calculate_checksum(sentence):
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

def handle_client(client_socket, station_name, tree, station_info):
    while not stop_event.is_set():
        try:
            data = client_socket.recv(1024)
            if not data:
                break
            print(f"Received from {station_name}: {data.decode('utf-8').strip()}")
        except Exception as e:
            print(f"Error handling client {station_name}: {e}")
            break
    client_socket.close()
    station_info["connected"] = False
    update_tree(tree, station_name, station_info)

def listen_wpl_and_broadcast(ser, stations, tree):
    while not stop_event.is_set():
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

def update_tree(tree, station_name, station_info):
    for child in tree.get_children():
        if tree.item(child, 'values')[0] == station_name:
            tree.item(child, values=(station_name, station_info["port"], station_info["connected"]))

def main(ser_port, expected_stations, log_text, tree):
    ser = serial.Serial(ser_port, 9600, timeout=1)
    base_port = 1234
    global stations
    stations = {}
    station_counter = 1

    log_text.insert(tk.END, f"Listening for GPWPL sentences to define up to {expected_stations} stations...\n")

    start_time = datetime.now()

    while (datetime.now() - start_time) < timedelta(minutes=3) and not stop_event.is_set():
        if len(stations) >= expected_stations:
            break

        line = ser.readline().decode('utf-8').strip()
        if line.startswith('$GPWPL'):
            log_text.insert(tk.END, f"Original GPWPL sentence: {line}\n")
            wpl_parts = line.split(',')
            if len(wpl_parts) >= 6:
                station_name = wpl_parts[5].split('*')[0]
                if station_name not in stations:
                    station_id = f"{station_counter:04d}"
                    port = base_port + station_counter - 1
                    station_counter += 1
                    stations[station_name] = {"id": station_id, "port": port, "socket": None, "client_socket": None, "connected": False}
                    tree.insert('', 'end', values=(station_name, port, stations[station_name]["connected"]))
                    log_text.insert(tk.END, f"Station {station_name} defined with ID {station_id} and port {port}\n")

    log_text.insert(tk.END, "Finished collecting station names. Now setting up server sockets and waiting for connections...\n")

    for station_name, station_info in stations.items():
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind(('localhost', station_info["port"]))
        server_socket.listen(1)
        station_info["socket"] = server_socket
        log_text.insert(tk.END, f"TCP server listening on localhost:{station_info['port']} for station {station_name}\n")

    for station_name, station_info in stations.items():
        client_socket, addr = station_info["socket"].accept()
        station_info["client_socket"] = client_socket
        station_info["connected"] = True
        update_tree(tree, station_name, station_info)
        log_text.insert(tk.END, f"Connection established with client for station {station_name} on {addr}\n")

        threading.Thread(target=handle_client, args=(client_socket, station_name, tree, station_info)).start()

    threading.Thread(target=listen_wpl_and_broadcast, args=(ser, stations, tree)).start()

def start_script():
    ser_port = port_var.get()
    expected_stations = int(stations_var.get())
    if not ser_port or not expected_stations:
        messagebox.showerror("Input Error", "Please select a port and enter the number of stations.")
        return
    log_text.insert(tk.END, "Starting script...\n")
    stop_event.clear()
    threading.Thread(target=main, args=(ser_port, expected_stations, log_text, tree)).start()

def stop_script():
    stop_event.set()
    log_text.insert(tk.END, "Stopping script...\n")
    global stations
    for station_info in stations.values():
        if station_info["client_socket"]:
            station_info["client_socket"].close()
        if station_info["socket"]:
            station_info["socket"].close()
    stations = {}
    log_text.insert(tk.END, "Script stopped.\n")
    log_text.delete(1.0, tk.END)  # Clear log messages
    for item in tree.get_children():
        tree.delete(item)  # Clear table

def refresh_ports():
    ports = [comport.device for comport in serial.tools.list_ports.comports()]
    port_dropdown['values'] = ports
    if ports:
        port_var.set(ports[0])

# Create GUI
root = tk.Tk()
root.title("Serial Port Listener")

main_frame = ttk.Frame(root, padding="10")
main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

port_var = tk.StringVar()
stations_var = tk.StringVar()

ttk.Label(main_frame, text="Select Port:").grid(row=0, column=0, sticky=tk.W)
port_dropdown = ttk.Combobox(main_frame, textvariable=port_var)
port_dropdown.grid(row=0, column=1, sticky=(tk.W, tk.E))
refresh_ports()

ttk.Label(main_frame, text="Number of Stations:").grid(row=1, column=0, sticky=tk.W)
ttk.Entry(main_frame, textvariable=stations_var).grid(row=1, column=1, sticky=(tk.W, tk.E))

start_button = ttk.Button(main_frame, text="Start", command=start_script)
start_button.grid(row=2, column=0, sticky=tk.W)

stop_button = ttk.Button(main_frame, text="Stop", command=stop_script)
stop_button.grid(row=2, column=1, sticky=tk.W)

log_text = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, width=50, height=15)
log_text.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))

tree = ttk.Treeview(main_frame, columns=("Station Name", "Port", "Connected"), show='headings')
tree.heading("Station Name", text="Station Name")
tree.heading("Port", text="Port")
tree.heading("Connected", text="Connected")
tree.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))

root.mainloop()
