#!/usr/bin/env python3
"""
Tempe High School Timetable Kiosk
Copyright (C) 2025 TempeHS

Licensed under the MIT License. See the LICENSE file for details.

Simple HTTP server for LISS Timetable Application
Serves files from the current directory to avoid CORS issues
"""
import http.server
import socketserver
import webbrowser
import os
import sys

PORT = 8000


class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers to allow local file access
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()


def main():
    # Change to the directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    print(f"Starting LISS Timetable Server on port {PORT}")
    print(f"Serving files from: {script_dir}")
    print(f"Open your browser to: http://localhost:{PORT}")
    print("Press Ctrl+C to stop the server")
    print("-" * 50)

    try:
        with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
            # Try to open browser automatically
            try:
                webbrowser.open(f'http://localhost:{PORT}')
            except:
                pass

            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except OSError as e:
        if e.errno == 48:  # Address already in use
            print(
                f"Port {PORT} is already in use. Try a different port or stop the other server.")
        else:
            print(f"Error starting server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
