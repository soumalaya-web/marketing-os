#!/usr/bin/env python3
import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

SUMMARY_PATH = os.path.expanduser("~/google-ads-agent/daily_summary.txt")
LOG_PATH = os.path.expanduser("~/google-ads-agent/logs/agent.log")


def _find(pattern, text, group=1, default=""):
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(group).strip() if m else default


def _extract_bullets(text, header_pattern):
    """Return list of quoted bullet-point values under a section header.

    Scans lines after the first line matching header_pattern, collecting
    lines of the form '  • 'value'' until a blank line or non-bullet line
    is hit.
    """
    lines = text.splitlines()
    collecting = False
    results = []
    for line in lines:
        if not collecting:
            if re.search(header_pattern, line, re.IGNORECASE):
                collecting = True
            continue
        stripped = line.strip()
        if not stripped:
            break
        m = re.match(r"^[•\-\*]\s*'(.+)'$", stripped)
        if m:
            results.append(m.group(1))
        elif stripped.startswith(('•', '-', '*')):
            # bullet without quotes — take the text after the bullet
            results.append(re.sub(r'^[•\-\*]\s*', '', stripped))
        else:
            break
    return results


def parse_summary(text):
    return {
        "impressions":             _find(r'([\d,]+)\s+impressions', text),
        "clicks":                  _find(r'([\d,]+)\s+clicks', text),
        "ctr":                     _find(r'CTR of\s+([\d.]+%)', text),
        "avg_cpc":                 _find(r'average CPC of\s+(\$[\d.]+)', text),
        "conversions":             "0",
        "today_spend":             _find(r'Spent today\s*:\s*(\$[\d.]+)', text),
        "cap_status":              _find(r'Cap status\s*:\s*(.+)', text),
        "negative_keywords_count": _find(r'Negative keywords added:\s*(\d+)', text),
        "pending_ads":             _find(r'Ad copy variants\s*:\s*(\d+)\s+pending', text),
        "pending_strength":        _find(r'Ad strength updates\s*:\s*(\d+)\s+pending', text),
        "copy_review_flags":       _find(r'(\d+)\s+ad\(s\)\s+flagged', text),
        "pid":                     _find(r'PID:\s*(\S+)', text),
        "last_run":                _find(r'Generated:\s*(\S+)', text),
        "next_run":                _find(r'Next run:\s*(\d{1,2}:\d{2})', text),
        "negative_keywords":       _extract_bullets(text, r'Negative keywords added:'),
        "positive_keywords":       _extract_bullets(text, r'Keywords auto-added'),
    }


class Handler(BaseHTTPRequestHandler):
    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/":
            self.serve_file("index.html", "text/html")
        elif self.path == "/api/summary":
            self.serve_summary()
        elif self.path == "/api/log":
            self.serve_log()
        elif self.path == "/api/clear-strength":
            self.serve_clear_strength()
        else:
            self.send_error(404)

    def serve_file(self, filename, content_type):
        try:
            with open(filename, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_error(404, f"{filename} not found")

    def serve_summary(self):
        try:
            subprocess.run(
                ["git", "-C", "/Users/soumalyachakraborty/google-ads-agent", "pull"],
                capture_output=True, text=True, timeout=15
            )
        except Exception:
            pass
        result = {}
        try:
            with open(SUMMARY_PATH, "r") as f:
                text = f.read()
            result = parse_summary(text)
        except FileNotFoundError:
            pass
        self.send_json(result)

    def serve_clear_strength(self):
        result = subprocess.run(
            ["python3", "/Users/soumalayachakraborty/google-ads-agent/main.py", "--approve-strength"],
            capture_output=True, text=True
        )
        self.send_json({"output": result.stdout + result.stderr})

    def serve_log(self):
        lines = []
        try:
            with open(LOG_PATH, "r") as f:
                lines = f.readlines()
            lines = [l.rstrip("\n") for l in lines[-50:]]
        except FileNotFoundError:
            pass
        self.send_json(lines)

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")


if __name__ == "__main__":
    server = HTTPServer(("", 8080), Handler)
    print("Serving on http://localhost:8080")
    server.serve_forever()
