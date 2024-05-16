import threading
import multiprocessing
import PySimpleGUI as gui
from trackerBackEnd import TrackerBackEnd

class TrackerFrontEnd:
    def __init__(self, host, port):
        self.trackerBackEnd = self._init_backend(host, port)
        self.window = self._create_window()

    def _init_backend(self, host, port):
        return TrackerBackEnd(
            host,
            port,
            log_callback=self.log_message,
            log_request_callback=self.log_request,
        )

    def _create_window(self):
        gui.theme('DarkBlue')
        layout = self._define_layout()
        return gui.Window('Tracker', layout, finalize=True)

    def _define_layout(self):
        tracker_controls = [
            [gui.Button('Start', key='-START_TRACKER-', font=('Helvetica', 12), button_color=('white', 'green')),
             gui.Button('Stop', key='-STOP_TRACKER-', font=('Helvetica', 12), button_color=('white', 'red')),
             gui.Text('Command Input:', font=('Helvetica', 12), pad=((20, 5), (3, 3))),
             gui.InputText(key='-COMMAND-', size=(20, 1), font=('Helvetica', 12)),
             gui.Button('Send', key='-PROCESS_COMMAND-', font=('Helvetica', 10))]
        ]

        tracker_logs_tab = [
            [gui.Text('Tracker Logs', font=('Helvetica', 16, 'bold'))],
            [gui.Multiline("", size=(60, 10), key='-LOG-', autoscroll=True, disabled=True, reroute_cprint=True, font=('Helvetica', 12))]
        ]

        peer_requests_tab = [
            [gui.Text('Peer Request Logs', font=('Helvetica', 16, 'bold'))],
            [gui.Multiline(size=(60, 10), key='-REQUEST_LOG-', disabled=True, autoscroll=True, font=('Helvetica', 12))]
        ]

        layout = [
            [gui.Frame('Tracker Controls', tracker_controls, font=('Helvetica', 14), title_color='White')],
            [gui.TabGroup([[gui.Tab('Tracker Logs', tracker_logs_tab), gui.Tab('Peer Requests', peer_requests_tab)]], tab_location='topleft', font=('Helvetica', 12))]
        ]

        return layout

    def start(self):
        self.trackerBackEnd.start()

    def stop(self):
        self.trackerBackEnd.stop()

    def handle_command(self, cmd):
        threading.Thread(target=self.trackerBackEnd.handle_command, args=(cmd,)).start()

    def log_message(self, msg):
        self._update_log("-LOG-", msg)

    def log_request(self, msg):
        self._update_log("-REQUEST_LOG-", msg)

    def _update_log(self, key, msg):
        self.window[key].update(disabled=False)
        self.window[key].print(msg, end="\n")
        self.window[key].update(disabled=True)


def handle_events(trackerGUI):
    while True:
        event, val = trackerGUI.window.read()
        if event == '-START_TRACKER-':
            trackerGUI.start()
        elif event == '-STOP_TRACKER-':
            trackerGUI.stop()
        elif event == '-PROCESS_COMMAND-':
            trackerGUI.handle_command(val["-COMMAND-"])
        elif event == gui.WINDOW_CLOSED:
            trackerGUI.window.close()
            break

if __name__ == '__main__':
    trackerGUI = TrackerFrontEnd("0.0.0.0", 8888)
    handle_events(trackerGUI)
