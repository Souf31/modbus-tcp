import websockets
from pymodbus.client import ModbusTcpClient
import time
import threading
import asyncio

# Configuration for the Modbus TCP connection
FACTORY_IO_IP = '192.168.56.1'  # IP address of Factory I/O
FACTORY_IO_PORT = 502  # Default Modbus TCP port for Factory I/O
SLAVE_ID = 1

# Create a Modbus client
client = ModbusTcpClient(FACTORY_IO_IP, port=FACTORY_IO_PORT)

# Global flag to stop all operations when 'trigger-bsod' is received
factory_broken = False
lock = threading.Lock()  # For thread-safe access to the factory_broken flag

# WebSocket handler function
async def websocket_handler(websocket, path):
    global client
    global factory_broken
    async for message in websocket:
        print(f"Received WebSocket message: {message}")
        if message == 'trigger-bsod':
            print("Received 'trigger-bsod' - Activating special coil")
            with lock:  # Lock while modifying the flag
                factory_broken = True  # Permanently stop all factory operations
                client.write_coil(0, True, SLAVE_ID)  # Break the factory - Conveyor stays ON


# Start WebSocket server (in a separate thread)
def start_websocket_server():
    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # Start the WebSocket server with the new event loop
    server = websockets.serve(websocket_handler, "localhost", 8765)
    loop.run_until_complete(server)

    # Indicate that the WebSocket server has started
    print("WebSocket server started on ws://localhost:8765")
    loop.run_forever()


def modbus_operations():
    if client.connect():
        print("Connected to Factory I/O Modbus server")
    else:
        print("Failed to connect to Modbus server")
        return

    # Coils 0 to 6 : Conveyer Entry, Load, Unload, TransfL, TransfR, ConvL, ConvR
    # Inputs 0 to 12: High Sensor, Low Sensor, Pallet Sensor, Loaded, At left Entry, At left exit, At right Entry, at right exit, start, reset, stop, emergency stop, auto

    # Step 1: Reset the whole factory conveyor and transfer states at the start
    client.write_coil(0, False, SLAVE_ID)  # Conveyor entry OFF
    client.write_coil(1, False, SLAVE_ID)  # Load OFF
    client.write_coil(2, False, SLAVE_ID)  # Unload OFF
    client.write_coil(3, False, SLAVE_ID)  # Transfer left OFF
    client.write_coil(4, False, SLAVE_ID)  # Transfer right OFF
    client.write_coil(5, False, SLAVE_ID)  # Conveyor left OFF
    client.write_coil(6, False, SLAVE_ID)  # Conveyor right OFF

    client.write_coil(0, True, SLAVE_ID)
    client.write_coil(1, True, SLAVE_ID)



    try:
        while True:

            with lock:
                if factory_broken:
                    print("Factory has been broken - stopping all Modbus operations")
                    break  # Exit the loop to stop all Modbus operations permanently

            response = client.read_discrete_inputs(0, 8, SLAVE_ID)

            high_sensor = response.bits[0]  # High sensor at coil 0 (adjust if needed)
            low_sensor = response.bits[1]  # Low sensor at coil 1 (adjust if needed)
            pallet_sensor = response.bits[2]
            loaded = response.bits[3]
            left_entry = response.bits[4]
            left_exit = response.bits[5]
            right_entry = response.bits[6]
            right_exit = response.bits[7]

            # print(f"High Sensor: {high_sensor}")
            # print(f"Low Sensor: {low_sensor}")
            # print(f"Pallet Sensor: {pallet_sensor}")
            # print(f"Loaded: {loaded}")
            # print("\n\n")

            # Step 2: Sorting Logic Based on Height
            if pallet_sensor:
                if low_sensor and not high_sensor:
                    high_package = False
                elif high_sensor and low_sensor:
                    high_package = True

            if loaded:  # If a part is loaded on the pallet
                client.write_coil(0, False, SLAVE_ID) #Stops the conveyer entry
                client.write_coil(1, False, SLAVE_ID) #Stops the load entry
                if not high_package:  # Small part (Low sensor active, High sensor inactive):
                    # print("Sorting small part - activating transfer left")
                    client.write_coil(3, True, SLAVE_ID)  # Activate transfer left

                elif high_package:
                    # print("Sorting large part - activating transfer right")
                    client.write_coil(4, True, SLAVE_ID)  # Activate transfer right

            if not left_exit or not right_exit:
                client.write_coil(0, True, SLAVE_ID)  # Starts the conveyer entry
                client.write_coil(1, True, SLAVE_ID)  # Starts the conveyer entry
                client.write_coil(3, False, SLAVE_ID)
                client.write_coil(4, False, SLAVE_ID)

            client.write_coil(5, True, SLAVE_ID)  # Starts the conveyer left
            client.write_coil(6, True, SLAVE_ID)  # Starts the conveyer right


    finally:
        client.close()
        print("Disconnected from Factory I/O Modbus server")

# Start the WebSocket server in a separate thread
websocket_thread = threading.Thread(target=start_websocket_server)
websocket_thread.daemon = True  # Daemon thread will exit when the main thread exits
websocket_thread.start()

# Start the Modbus operations in the main thread
modbus_operations()