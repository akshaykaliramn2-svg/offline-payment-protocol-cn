import socket
import threading
import unittest

from opp.protocol import make_message, recv_frame, send_frame


class ProtocolTests(unittest.TestCase):
    def test_length_prefixed_round_trip(self):
        left, right = socket.socketpair()
        try:
            message = make_message("PING", {"text": "offline payment"}, "msg-1")
            thread = threading.Thread(target=send_frame, args=(left, message))
            thread.start()
            received = recv_frame(right)
            thread.join()
            self.assertEqual(received, message)
        finally:
            left.close()
            right.close()

    def test_rejects_wrong_version(self):
        left, right = socket.socketpair()
        try:
            # Construct a well-framed JSON body with an unsupported version.
            import json
            import struct
            body = json.dumps({"protocol": "OPP", "version": "99", "type": "PING", "payload": {}}).encode()
            left.sendall(struct.pack("!I", len(body)) + body)
            with self.assertRaises(ValueError):
                recv_frame(right)
        finally:
            left.close()
            right.close()


if __name__ == "__main__":
    unittest.main()
