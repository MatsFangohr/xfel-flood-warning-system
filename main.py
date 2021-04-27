import seeed_relay_v1
import logging as log
import gsmmodem
import dotenv
import time
import json
import os

dotenv.load_dotenv()
          
logging = False
debug = True

class WaterAlarm:
    def __init__(self,
                 alert_phone_numbers: list,
                 phone_number: str,
                 request_message: str = "Water?",
                 water_message: str = "1",
                 no_water_message: str = "0",
                 relay_board_address = 0x20,
                 baudrate: int = 19200,
                 red_relay: int = 1,
                 amber_relay: int = 2,
                 green_relay: int = 3,
                 disconnect_time: int = 10,
                 water_time: int = 10,
                 log_everything: bool = True):
        """Communicates with another device via SMS. If it returns a certain
         value after a certain request, turns a certain relay on. Can also
         send messages to people to inform them of the situation. In this
         case, it communicates with a water sensor.

        phone_number: The phone number to communicate with.
        request_message: The message to send to the other device to request its status. Defaults to "Water?".
        water_message: The expected return message when water is detected. Defaults to "1".
        no_water_message: The expected return message when no water is detected. Defaults to "0".
        relay_board_address: Hardware address of the relay board. Defaults to 0x20.
        baudrate: The baudrate of the serial port to the cellular modem.
        red_relay: The number of the relay connected to the red light. Defaults to 1.
        amber_relay: The number of the relay connected to the amber light. Defaults to 2.
        green_relay: The number of the relay connected to the green light. Defaults to 3.
        alert_phone_numbers: The phone numbers to alert when signal is lost or water is detected.
        disconnect_time: The time in minutes to wait before signalling a disconnect. Must be a multiple of 2. Defaults to 10.
        water_time: The time in minutes that water must be detected for before signalling water. Must be a muliple of 2. Defaults to 10.
        log_everything: Logs the sending and receiving of messages to the console. Errors, disconnects and water detections are always logged. Defaults to True.

        Call the mainloop method to start the communication.
        """
        self.phone_number = phone_number
        self.request_message = request_message
        self.water_message = water_message
        self.no_water_message = no_water_message
        self.relay_board_address = relay_board_address
        self.red_relay = red_relay
        self.amber_relay = amber_relay
        self.green_relay = green_relay
        self.alert_numbers = alert_phone_numbers
        self.water_time = water_time
        self.disconnect_time = disconnect_time
        self.log = log_everything
        self.debug = debug
        if self.disconnect_time % 2 != 0:
            raise ValueError("'water_time' must be a multiple of 2!")
        if self.disconnect_time % 2 != 0:
            raise ValueError("'disconnect_time' must be a multiple of 2!")
        if self.log:
            print("Connecting modem")
        connected = False
        while connected == False:
            try:
                self.modem = gsmmodem.GsmModem("/dev/ttyS0", baudrate)
                self.modem.connect()
                connected = True
            except Exception as e:
                self.exception_handler(e, "connecting the modem. Trying again")
        if self.log:
            print("Connecting relay board")
        self.relay_board = seeed_relay_v1.Relay(device_address=relay_board_address)
        self.missing_responses = 0
        self.water = False
        self.times_water_detected = 0
        self.relay_board.on(red_relay)
        time.sleep(1)
        self.relay_board.off(red_relay)
        self.relay_board.on(amber_relay)
        time.sleep(1)
        self.relay_board.off(amber_relay)
        self.relay_board.on(green_relay)
        time.sleep(1)
        self.relay_board.off(green_relay)

    def request_status(self):
        """Sends a message to the given number to check for water."""
        self.send_message(self.phone_number, self.request_message)
        self.missing_loops = 0
        self.awaiting_message = True
        if self.log:
            print("Sent request.")

    def check_for_answer(self):
        """Checks if the other device has sent an answer yet."""
        try:
            messages = self.modem.listStoredSms(delete=True)
        except Exception as e:
            self.exception_handler(e, "checking for new messages")
            messages = []
        if len(messages) == 0 and self.awaiting_message:
            self.missing_loops += 1
        for message in messages:
            self.parse_message(message)

    def parse_message(self, message):
        """Turns relays on and off depending on the message contents. 'message' should be a gsmmodem SMS object."""
        if message.number == self.phone_number:
            if self.missing_responses >= self.disconnect_time / 2:
                self.alert_humans("restored")
            self.missing_loops = 0
            self.missing_responses = 0
            self.awaiting_message = False
            if message.text == self.water_message:
                self.times_water_detected += 1
                self.update_status()
            elif message.text == self.no_water_message:
                self.times_water_detected = 0
                self.update_status()
            else:
                print(f"Unknown message '{message.text}'")
        else:
            print(f"Unknown number {message.number}")

    def update_status(self):
        """Handles the aount of times water needs to be detected."""
        if self.times_water_detected == 0:
            self.light("green")
            if self.water:
                self.alert_humans("removed")
            self.water = False
            if self.log:
                print(f"Received '{self.no_water_message}', turning green light on.")
        elif 0 < self.times_water_detected < self.water_time / 2:
            print(f"Water has been detected for {self.times_water_detected * 2}m. Will alert others at {self.water_time}m.")
        elif self.times_water_detected >= self.water_time / 2:
            self.light("red")
            self.alert_humans("water")
            self.water = True
            print(f"Water has been detected for the past {self.times_water_detected * 2}m, turning red light on.")
    
    def exception_handler(self, e, task):
        """Logs exceptions."""
        print(f"Encountered a {e.__class__.__name__} while {task}.")
        if not self.relay_board.get_port_status(self.amber_relay):
            self.relay_board.on(self.amber_relay)
            time.sleep(1)
            self.relay_board.off(self.amber_relay)
        if self.log:
            try:
                print(f"Signal strength: {modem.signalStrength} / 100")
            except Exception as e:
                print("Unable to get signal strength.")

    def light(self, light):
        """Manages the lights"""
        if light == "red":
            self.relay_board.off(self.amber_relay)
            self.relay_board.off(self.green_relay)
            self.relay_board.on(self.red_relay)
        elif light == "amber":
            self.relay_board.off(self.green_relay)
            # self.relay_board.off(self.red_relay) - this is commented in case water is detected and then the connection is lost - now it will keep the red light
            self.relay_board.on(self.amber_relay)
        elif light == "green":
            self.relay_board.off(self.amber_relay)
            self.relay_board.off(self.red_relay)
            self.relay_board.on(self.green_relay)
        else:
            print(f"Unknown light {light}.")

    def alert_humans(self, event: str):
        """Alerts all phone numbers on the 'alert_numbers' list to a given event."""
        for number in self.alert_numbers:
            if event == "water":
                self.send_message(number, f"Water has been detected at XFEL for the past {self.times_water_detected * 2}m!")
            elif event == "disconnect":
                self.send_message(number, f"The connection to the flood monitoring system at XFEL has been lost for {self.missing_responses * 2}m.")
            elif event == "restored":
                self.send_message(number, "The connection to the flood monitoring system has been restored.")
            elif event == "removed":
                self.send_message(number, "The water is no longer detected.")
            else:
                raise ValueError(f"Unknown event {event}")

    def send_message(self, number : str, message : str):
        try:
            self.modem.sendSms(number, message)
        except Exception as e:
            self.exception_handler(e, f"sending message '{message}' to {number}")

    def mainloop(self):
        """The main program."""
        try:
            while True:
                for i in range(12):
                    if i == 0:
                        self.request_status()
                    if debug:
                        time.sleep(2)
                    else:
                        time.sleep(10)
                    self.check_for_answer()
                if self.missing_loops == 12:  # full loop without a response
                    self.missing_responses += 1
                    print(f"No answer received in the last {self.missing_responses * 2}m!")
                if self.missing_responses >= self.disconnect_time / 2:
                    print(f"No answer received in the last {self.missing_responses * 2} minutes, turning amber light on.")
                    self.light("amber")
                    self.alert_humans("disconnect")
        finally:
            self.relay_board.all_off()
            self.modem.close()
if logging:
    log.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)

phone_number = os.environ["phone_number"]
alert_phone_numbers = json.loads(os.environ["alert_phone_numbers"])

wateralarm = WaterAlarm(
    phone_number=phone_number,
    request_message="Water?",
    water_message="1",
    no_water_message="0",
    relay_board_address=0x20,
    baudrate = 19200,
    red_relay=1,
    amber_relay=2,
    green_relay=3,
    log_everything=True,
    alert_phone_numbers=alert_phone_numbers,
    disconnect_time=10,
    water_time=4 
    )

wateralarm.mainloop()
