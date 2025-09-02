import socket,sys
host='db.xsglqqywodyqhzktkygq.supabase.co'
port=5432
try:
    print('getaddrinfo:', socket.getaddrinfo(host, port))
    s=socket.create_connection((host,port),timeout=5)
    s.close()
    print('TCP: OK')
except Exception as e:
    print('ERR:', e)
    sys.exit(1)
