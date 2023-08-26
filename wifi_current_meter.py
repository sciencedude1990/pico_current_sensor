from machine import ADC, Pin, Timer
import time
import network
import socket
import math

# wifi_info is a wifi_info.py file with variables ssid = '...', and wifi_password = '...'
import wifi_info     

# A class to IIR average measurements
class IIRMeasurement:
    def __init__(self, alpha):
        # The IIR state variable
        self.prev = 0;
        
        # Constants for filtering
        self.alpha = alpha
        
        self.alpha_1 = 1 - alpha
        
    def reset(self):
        self.prev = 0;
        
    def value(self):
        return self.prev
        
    def __str__(self):
        # To string
        return "IIR: " + str(self.prev)
    
    def update(self, new_value):    
        # Update the state variable
        self.prev = self.prev * self.alpha_1 + new_value * self.alpha
        
# Objects to track the average values        
adc_5A_average = IIRMeasurement(0.03125)
adc_20A_average = IIRMeasurement(0.03125)

# Objects to track the RMS values
adc_5A_rms_average = IIRMeasurement(0.005)
adc_20A_rms_average = IIRMeasurement(0.005)

# The DC offset for the current meters
adc_5A_zero = 33044.0
adc_20A_zero = 33183.0

# Sensitivity - see page 2 of MCS1806GS.pdf - i.e., the MCS1806 datasheet
adc_5A_sensitivity = (3.3 / 65536) / 264e-3
adc_20A_sensitivity = (3.3 / 65536) / 66e-3

# Create the ADCs
adc_5A = ADC(Pin(28))
adc_20A = ADC(Pin(27))

# The routing for reading the ADCs
def read_ADC_timer(t):
    # Bring in the defines
    global adc_5A_average, adc_20A_average, adc_5A_rms_average, adc_20A_rms_average
    global adc_5A_zero, adc_20A_zero, adc_5A, adc_20A
    
    # Read the ADCs
    adc_5A_read = adc_5A.read_u16()
    adc_20A_read = adc_20A.read_u16()
        
    # Remove the DC offset
    adc_5A_dc_correct = adc_5A_read - adc_5A_zero
    adc_20A_dc_correct = adc_20A_read - adc_20A_zero
                
    # Update the average object
    adc_5A_average.update(adc_5A_dc_correct)
    adc_20A_average.update(adc_20A_dc_correct)
        
    # Update the RMS object
    adc_5A_rms_average.update(adc_5A_dc_correct * adc_5A_dc_correct)
    adc_20A_rms_average.update(adc_20A_dc_correct * adc_20A_dc_correct)
                
# Replace with your own SSID and WIFI password
ssid = wifi_info.ssid
wifi_password = wifi_info.wifi_password
my_ip_addr = '192.168.0.25'

# Please see https://docs.micropython.org/en/latest/library/network.WLAN.html
# Try to connect to WIFI
wlan = network.WLAN(network.STA_IF)
wlan.active(True)

# Specify the IP address
wlan.ifconfig((my_ip_addr, '255.255.255.0', '192.168.0.1', '8.8.8.8'))

# Connect
wlan.connect(ssid, wifi_password)

# Wait for connect or fail
max_wait = 10
while max_wait > 0:
    if wlan.status() < 0 or wlan.status() >= 3:
        break
    max_wait -= 1
    print('waiting for connection...')    
    time.sleep(1)
    
# Handle connection error
if wlan.status() != 3:
    # Connection to wireless LAN failed
    print('Connection failed, reset in 5 seconds')
    time.sleep(5)
    machine.reset()    
    
else:
    print('Connected')
    status = wlan.ifconfig()
    print( 'ip = ' + status[0] )

# Open socket
addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

# Try to bind the socket
try:
    s.bind(addr)
        
except:
    print('Bind Failed - waiting 5 seconds and then will reset');    
    time.sleep(5)
    machine.reset()
    
# Listen
s.listen(4)
print('listening on', addr)

# Timeout for the socket accept, i.e., s.accept()
s.settimeout(3)

# Kick off ADC timer
print("Starting ADC timer...")
tim = Timer(freq = 10000, mode = Timer.PERIODIC, callback = read_ADC_timer)


# Listen for connections, serve up web page
while True:
    
    # Handle connection error
    if wlan.status() != 3:
        # Connection to wireless LAN failed
        print('Connection failed during regular operation - go for reset')
        time.sleep(5)
        machine.reset()
        
    # Main loop
    accept_worked = 0
    try:
        print("Run s.accept()")
        cl, addr = s.accept()
        accept_worked = 1
    except:  
        # Nobody connected
        print("No connect...")
        # If running Thonny - let's the Thonny "Stop" button work
        time.sleep(0.5)
        
    if accept_worked == 1:
        # Exciting - somebody is looking for a webpage!
        try:
            print('client connected from', addr)
            request = cl.recv(1024)
            print("request:")
            print(request)
            request = str(request)
                    
            # Copy the measurements
            avg_5A = adc_5A_average.value()
            avg_20A = adc_20A_average.value()
            
            rms_5A = adc_5A_rms_average.value()
            rms_20A = adc_20A_rms_average.value()
                   
            # Default response                        
            response = "<HTML><HEAD><TITLE>WIFI current meter</TITLE></HEAD><BODY><h1>WIFI Current Meter</h1><br>5A avg: " + str(avg_5A * adc_5A_sensitivity) + " A <br>20A avg: " + str(avg_20A * adc_20A_sensitivity) + " A <br>5A rms (5 Hz): " + str(math.sqrt(rms_5A) * adc_5A_sensitivity) + " A <br>20A rms (5 Hz): " + str(math.sqrt(rms_20A) * adc_20A_sensitivity) + " A</BODY></HTML>"
            
            # Send it!
            cl.send('HTTP/1.0 200 OK\r\nContent-Length: ' + str(len(response)) + '\r\nConnection: Keep-Alive\r\n\r\n')
            cl.sendall(response)
                
            cl.close()
            
        except OSError as e:
            cl.close()
            print('connection closed')
            
