import os
BUFFER_SIZE=1048576
def to_hex(data):
    import binascii, pickle
    if isinstance(data, str):data = str_to_bytes(data)
    if not isinstance(data, (bytes, bytearray)):data = pickle.dumps(data)
    chunk_size = BUFFER_SIZE
    return ''.join([binascii.hexlify(data[i:i + chunk_size]).decode('utf-8') for i in range(0, len(data), chunk_size)])
def from_hex(data):
    import binascii
    if isinstance(data, (bytes, bytearray)):data=bytes_to_str(data)
    try:return b''.join([binascii.unhexlify(data[i:i + BUFFER_SIZE * 2]) for i in range(0, len(data), BUFFER_SIZE * 2)])
    except:return b''
def str_to_bytes(data):
    import numpy as np
    if isinstance(data,bytes):return data
    return bytes(np.frombuffer(data.encode('latin1'), dtype=np.uint8))
def bytes_to_str(data):
    try:data=data.tobytes()
    except:pass
    try:data=data.decode('latin1')
    except:pass
    return data