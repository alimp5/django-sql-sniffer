import argparse
import signal
import time
from multiprocessing.connection import Listener
from django_sql_sniffer import analyzer, injector, sniffer


def main():
    # parse arguments
    parser = argparse.ArgumentParser(description="Analyze SQL queries originating from a running process.")
    parser.add_argument("-p", "--pid", help="The id of the process executing Django SQL queries.")
    parser.add_argument("-v", "--verbose", action='store_true', help="Verbose mode - enables non-SQL logging on server and client (injected) side.")
    parser.add_argument("-t", "--tail", action='store_true', help="Log SQL queries as they are executed in tail mode.")
    args = parser.parse_args()

    # create socket and listen for a connection
    listener = Listener(('localhost', 0))  # will force OS to assign a random available port
    _, port = listener.address
    print(f"[{__file__}] listening on port {port}")

    # inject sniffer monkey patch
    with open(sniffer.__file__, "r") as source_file:
        source_code = source_file.read()
        code_to_inject = source_code.replace("PORT = 0", f"PORT = {port}")
        code_to_inject = code_to_inject.replace("LOGGING_ENABLED = False", f"LOGGING_ENABLED = {args.verbose}")
        code_to_inject += "sniffer.start()"
    injector.inject(str(args.pid), code_to_inject, args.verbose)

    # wait for callback
    print(f"[{__file__}] SQL sniffer injected, waiting for a reply")
    conn = listener.accept()
    listener.close()

    # receive and analyze executed SQL
    print(f"[{__file__}] reply received, sniffer active")
    sql_analyzer = analyzer.SQLQueryAnalyzer(conn, tail=args.tail)
    signal.signal(signal.SIGTERM, sql_analyzer.stop)
    signal.signal(signal.SIGINT, sql_analyzer.stop)
    sql_analyzer.start()
    while sql_analyzer.is_alive():
        time.sleep(0.5)
    injector.inject(str(args.pid), "sniffer.stop()", args.verbose)
    sql_analyzer.print_summary()


if __name__ == "__main__":
    main()