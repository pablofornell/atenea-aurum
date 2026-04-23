//+------------------------------------------------------------------+
//| socket-library-mt4-mt5.mqh — TCP/IP Socket library for MQL4/MQL5 |
//| Author: EJ Traderт | Source: mql5.com/en/blogs/post/706665       |
//| Wraps Windows Winsock API (kernel32.dll, wsock32.dll)            |
//+------------------------------------------------------------------+
#ifndef __SOCKET_LIBRARY_MQ4_MQ5__
#define __SOCKET_LIBRARY_MQ4_MQ5__

#define INVALID_SOCKET -1
#define SOCKET_ERROR -1
#define INADDR_NONE 0xffffffff

// Address family
#define AF_INET 2

// Socket type
#define SOCK_STREAM 1

// Socket options
#define SOL_SOCKET 0xffff
#define SO_REUSEADDR 4

// Socket flags
#define MSG_PEEK 2

// Protocols
#define IPPROTO_TCP 6

#ifdef __MQL4__
   #define uint unsigned int
   #define uint16_t unsigned short
   #define uint32_t unsigned int
#endif

//+------------------------------------------------------------------+
// DLL imports (Winsock API)
//+------------------------------------------------------------------+
#import "kernel32.dll"
   void *LocalAlloc(uint flags, uint size);
   bool LocalFree(void *ptr);
   void *memcpy(void *dest, void *src, uint count);
   void *memset(void *dest, int c, uint count);
   uint strlen(char &src[]);
#import

#import "wsock32.dll"
   // Socket functions
   uint socket(int af, int type, int protocol);
   bool closesocket(uint sock);

   // Network I/O
   int send(uint sock, uchar &buf[], int len, int flags);
   int recv(uint sock, uchar &buf[], int len, int flags);
   int recvfrom(uint sock, uchar &buf[], int len, int flags, void *addr, int *addrlen);
   int sendto(uint sock, uchar &buf[], int len, int flags, void *addr, int addrlen);

   // Connect/bind/listen
   int connect(uint sock, void *addr, int addrlen);
   int bind(uint sock, void *addr, int addrlen);
   int listen(uint sock, int backlog);
   uint accept(uint sock, void *addr, int *addrlen);

   // Address conversion
   uint inet_addr(char &ip[]);
   char *inet_ntoa(uint addr);

   // Utility
   int ioctlsocket(uint sock, uint cmd, uint &arg);
   int getsockname(uint sock, void *addr, int *addrlen);
   int getpeername(uint sock, void *addr, int *addrlen);
   int getsockopt(uint sock, int level, int optname, uchar &optval[], int *optlen);
   int setsockopt(uint sock, int level, int optname, uchar &optval[], int optlen);

   // Error handling
   int WSAGetLastError();
   void WSASetLastError(int error);
   char *WSAStrError(int error);
#import

//+------------------------------------------------------------------+
// sockaddr_in structure for IPv4
//+------------------------------------------------------------------+
struct sockaddr_in {
   uint16_t sin_family;
   uint16_t sin_port;
   uint32_t sin_addr;
   char sin_zero[8];
};

//+------------------------------------------------------------------+
// ClientSocket class
//+------------------------------------------------------------------+
class ClientSocket {
private:
   uint m_socket;
   string m_recv_buffer;

public:
   ClientSocket(uint socket_handle) : m_socket(socket_handle) {}

   ~ClientSocket() {
      if (m_socket != INVALID_SOCKET) {
         closesocket(m_socket);
         m_socket = INVALID_SOCKET;
      }
   }

   bool IsSocketConnected() {
      if (m_socket == INVALID_SOCKET) return false;
      uchar dummy[1];
      int result = recv(m_socket, dummy, 0, MSG_PEEK);
      if (result == SOCKET_ERROR) {
         return false;
      }
      return true;
   }

   bool Send(string data) {
      if (m_socket == INVALID_SOCKET) return false;

      uchar buf[];
      StringToCharArray(data, buf);
      int result = send(m_socket, buf, StringLen(data), 0);
      return result != SOCKET_ERROR;
   }

   string Receive(string delimiter = "\n") {
      if (m_socket == INVALID_SOCKET) return "";

      uchar buf[4096];
      int bytes = recv(m_socket, buf, 4096, 0);
      if (bytes <= 0) return "";

      string data = CharArrayToString(buf, 0, bytes);

      // Look for delimiter
      int pos = StringFind(data, delimiter);
      if (pos >= 0) {
         string result = StringSubstr(data, 0, pos);
         m_recv_buffer = StringSubstr(data, pos + StringLen(delimiter));
         return result;
      }

      m_recv_buffer += data;
      return "";
   }

   uint GetSocket() {
      return m_socket;
   }
};

//+------------------------------------------------------------------+
// ServerSocket class
//+------------------------------------------------------------------+
class ServerSocket {
private:
   uint m_socket;
   bool m_created;

public:
   ServerSocket(uint port, bool localhost = true) : m_created(false) {
      m_socket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
      if (m_socket == INVALID_SOCKET) {
         return;
      }

      // Enable SO_REUSEADDR
      uint reuse = 1;
      uchar reuse_buf[4];
      reuse_buf[0] = reuse & 0xFF;
      reuse_buf[1] = (reuse >> 8) & 0xFF;
      reuse_buf[2] = (reuse >> 16) & 0xFF;
      reuse_buf[3] = (reuse >> 24) & 0xFF;
      setsockopt(m_socket, SOL_SOCKET, SO_REUSEADDR, reuse_buf, 4);

      sockaddr_in addr;
      addr.sin_family = AF_INET;
      addr.sin_port = ((port & 0xFF) << 8) | ((port >> 8) & 0xFF); // htons
      addr.sin_addr = localhost ? inet_addr("127.0.0.1") : inet_addr("0.0.0.0");

      if (bind(m_socket, &addr, sizeof(addr)) == SOCKET_ERROR) {
         closesocket(m_socket);
         m_socket = INVALID_SOCKET;
         return;
      }

      if (listen(m_socket, 5) == SOCKET_ERROR) {
         closesocket(m_socket);
         m_socket = INVALID_SOCKET;
         return;
      }

      m_created = true;
   }

   ~ServerSocket() {
      if (m_socket != INVALID_SOCKET) {
         closesocket(m_socket);
         m_socket = INVALID_SOCKET;
      }
   }

   bool Created() {
      return m_created;
   }

   ClientSocket *Accept() {
      if (m_socket == INVALID_SOCKET) return NULL;

      sockaddr_in addr;
      int addr_len = sizeof(addr);
      uint client_socket = accept(m_socket, &addr, &addr_len);

      if (client_socket == INVALID_SOCKET) {
         return NULL;
      }

      return new ClientSocket(client_socket);
   }
};

#endif // __SOCKET_LIBRARY_MQ4_MQ5__
