import requests
import board
import digitalio
import json
import neopixel
import asyncio
from queue import Queue
import time

pixels = neopixel.NeoPixel(pin=board.D21, n=4, pixel_order='BRG')
c_yellow = (255, 255, 0)
c_red = (255, 0, 0)
c_green = (0, 255, 0)
c_purple = (255, 0, 255)
fade_steps = 30
fade_duration = 1

flmnt_switch = digitalio.DigitalInOut(board.D16)
flmnt_switch.direction = digitalio.Direction.INPUT
flmnt_switch.pull = digitalio.Pull.DOWN

# Set OctoPuppet API key in the header. Hostname is assumed localhost.
hostname = '127.0.0.1'
url = 'http://{}:5000/api/job'.format(hostname)
headers = {
    'X-Api-Key': 'OC_API_KEY',
}

# Set FabApp info: URL to flud.php and device id.
fa_url = 'FA_FLUD_URL'
fa_payload = json.dumps({
  "device_id": "DEV_ID",
  "type": "device_status"
})

fa_headers = {
  'Authorization': 'FA_API_KEY',
  'Content-Type': 'application/json'
}

fa_check_interval = 5  # Check transaction status every 5 seconds
txn_state = None

# Get transaction state
async def get_fa_status():
    fa_response = requests.request("POST", fa_url, headers=fa_headers, data=fa_payload)
    txn = fa_response.json()
    txn_state = txn.get('transaction_state', '')
    return txn_state

# Function to apply LED effect for Progress bar
async def led_effect_progress_bar(progress_percentage, printer_state):
    # Calculate the number of LEDs to light up based on the progress
    num_leds = int(progress_percentage / 25) + 1

    # Turn on the LEDs for the current progress segment (in yellow color)
    for i in range(num_leds):
        pixels[i] = c_yellow

    # If the printer is in Printing state and the progress is not 0%, add fading effect to the last active pixel
    if printer_state == 'Printing' and num_leds > 0:
        last_led = num_leds - 1

        # Fade
        for brightness in range(0, 256, int(255 / fade_steps)):
            pixels[last_led] = (int(c_yellow[0] - brightness), int(c_yellow[1] - brightness), 0)
            await asyncio.sleep(fade_duration / fade_steps)

        # Fade-out
        for brightness in range(255, -1, -(int(255 / fade_steps))):
            pixels[last_led] = (int(c_yellow[0] - brightness), int(c_yellow[1] - brightness), 0)
            await asyncio.sleep(fade_duration / fade_steps)

    # Turn off the remaining LEDs
    pixels[num_leds:len(pixels)] = [(0, 0, 0)] * (len(pixels) - num_leds)


# Function to apply LED effect for Printer Operational state
async def led_effect_operational():
    pixels.fill(c_green)  # Green color for Printer Operational

async def led_effect_offline():
    pixels.fill(c_red)

# Function to apply LED effect for Printer Error state
async def led_effect_error():
    pixels.fill(c_red)  # Red color for Printer Error
    for brightness in range(0, 256, int(255 / fade_steps)):
        pixels.fill((int(c_red[0] - brightness), 0, 0))
        await asyncio.sleep(fade_duration / fade_steps)

    # Fade-out
    for brightness in range(255, -1, -(int(255 / fade_steps))):
        pixels.fill((int(c_red[0] - brightness), 0, 0))
        await asyncio.sleep(fade_duration / fade_steps)

# Function to apply LED effect for Printer Moveable state
async def led_effect_moveable():
    pixels.fill(c_purple)  # Purple color for Movable state

    for brightness in range(0, 256, int(255 / fade_steps)):
        pixels.fill((int(255 - brightness), 0, int(255 - brightness)))
        await asyncio.sleep(fade_duration / fade_steps)

    # Fade-out
    for brightness in range(255, -1, -(int(255 / fade_steps))):
        pixels.fill((int(255 - brightness), 0, int(255 - brightness)))
        await asyncio.sleep(fade_duration / fade_steps)


# Function to get printer status and update LED effects
async def get_printer_status():
    try:
        effects_queue = Queue()
        last_fa_check_time = 0

        while True:
            response = requests.request("GET", url, headers=headers)
            data = response.json()

            printer_state = data['state']
            progress_percentage = data['progress']['completion'] if 'progress' in data and 'completion' in data['progress'] else 0

            # Get transaction state every 5 seconds
            current_time = asyncio.current_task()._loop.time()

            # Check transaction state if interval has passed
            if current_time - last_fa_check_time >= fa_check_interval:
                txn_state = await get_fa_status()
                last_fa_check_time = current_time

            # Add LED effects to the queue based on printer state priority
            if flmnt_switch.value != 1:
                if printer_state == 'Error':
                    effects_queue.put(led_effect_error())
                elif printer_state == 'Offline':
                    effects_queue.put(led_effect_offline())
                elif printer_state == 'Printing':
                    effects_queue.put(led_effect_progress_bar(progress_percentage, printer_state))
                elif printer_state == 'Paused':
                    effects_queue.put(led_effect_error())
                elif printer_state == 'Operational':
                    if txn_state == 'moveable':
                        effects_queue.put(led_effect_moveable())
                    else:
                        effects_queue.put(led_effect_operational())
            else:
                effects_queue.put(led_effect_error())
            print(f'Printer State: {printer_state}, Progress: {progress_percentage}, Transaction State: {txn_state}, Filament Switch: {flmnt_switch.value}')


            await asyncio.sleep(1)
            # Run the LED effect at the front of the queue (highest priority)
            if not effects_queue.empty():
                await effects_queue.get()
    except KeyboardInterrupt:
        # When the user interrupts the program, turn off the LEDs and exit gracefully
        pixels.fill((0, 0, 0))

# Run the program asynchronously
asyncio.run(get_printer_status())
