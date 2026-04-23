//+------------------------------------------------------------------+
//| AURUM_Bridge.mq4 — TCP command server for Python trading agent   |
//| Direct Winsock DLL implementation (no external headers)          |
//+------------------------------------------------------------------+
#property strict

#define MAGIC_NUMBER 20240101
#define SERVER_PORT 5555
#define TIMER_MS 100

// Winsock constants
#define AF_INET 2
#define SOCK_STREAM 1
#define IPPROTO_TCP 6
#define INVALID_SOCKET -1
#define SOCKET_ERROR -1
#define SOL_SOCKET 0xffff
#define SO_REUSEADDR 4
#define SOMAXCONN 5
#define FIONBIO 0x8004667E

// Global socket handles
int g_server_socket = INVALID_SOCKET;
int g_client_socket = INVALID_SOCKET;
string g_recv_buffer = "";

//+------------------------------------------------------------------+
// Winsock DLL imports
//+------------------------------------------------------------------+
#import "wsock32.dll"
   int socket(int af, int type, int protocol);
   int closesocket(int sock);
   int bind(int sock, uchar &addr[], int addrlen);
   int listen(int sock, int backlog);
   int accept(int sock, uchar &addr[], int &addrlen);
   int recv(int sock, uchar &buf[], int len, int flags);
   int send(int sock, uchar &buf[], int len, int flags);
   int inet_addr(uchar &ip[]);
   int setsockopt(int sock, int level, int optname, uchar &optval[], int optlen);
   int ioctlsocket(int sock, uint cmd, uint &arg);
#import
#import "ws2_32.dll"
   int WSAGetLastError();
#import
#define WSAEWOULDBLOCK 10035

//+------------------------------------------------------------------+
// sockaddr_in structure for IPv4
//+------------------------------------------------------------------+
struct sockaddr_in {
   ushort sin_family;
   ushort sin_port;
   uint sin_addr;
   char sin_zero[8];
};

//+------------------------------------------------------------------+
// Serialize sockaddr_in struct to byte array
//+------------------------------------------------------------------+
void SerializeSockaddr(sockaddr_in &addr, uchar &buf[])
{
   ArrayResize(buf, 16);
   buf[0] = (uchar)(addr.sin_family & 0xFF);
   buf[1] = (uchar)((addr.sin_family >> 8) & 0xFF);
   buf[2] = (uchar)(addr.sin_port & 0xFF);
   buf[3] = (uchar)((addr.sin_port >> 8) & 0xFF);
   buf[4] = (uchar)(addr.sin_addr & 0xFF);
   buf[5] = (uchar)((addr.sin_addr >> 8) & 0xFF);
   buf[6] = (uchar)((addr.sin_addr >> 16) & 0xFF);
   buf[7] = (uchar)((addr.sin_addr >> 24) & 0xFF);
   for (int i = 0; i < 8; i++) buf[8 + i] = (uchar)addr.sin_zero[i];
}

//+------------------------------------------------------------------+
// Convert string to byte array
//+------------------------------------------------------------------+
int StringToBytes(string s, uchar &buf[])
{
   int len = StringLen(s);
   ArrayResize(buf, len + 1);
   for (int i = 0; i < len; i++) {
      buf[i] = (uchar)StringGetChar(s, i);
   }
   buf[len] = 0;
   return len + 1;
}

//+------------------------------------------------------------------+
int OnInit()
{
   // Create socket
   g_server_socket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
   if (g_server_socket == INVALID_SOCKET) {
      Print("[AURUM] Failed to create socket");
      return INIT_FAILED;
   }

   // Set non-blocking mode so accept/recv don't freeze MT4's main thread
   uint nb = 1;
   ioctlsocket(g_server_socket, FIONBIO, nb);

   // Set SO_REUSEADDR
   uint reuse = 1;
   uchar reuse_buf[4];
   reuse_buf[0] = (uchar)(reuse & 0xFF);
   reuse_buf[1] = (uchar)((reuse >> 8) & 0xFF);
   reuse_buf[2] = (uchar)((reuse >> 16) & 0xFF);
   reuse_buf[3] = (uchar)((reuse >> 24) & 0xFF);
   setsockopt(g_server_socket, SOL_SOCKET, SO_REUSEADDR, reuse_buf, 4);

   // Prepare address
   sockaddr_in addr;
   addr.sin_family = AF_INET;
   addr.sin_port = (ushort)(((SERVER_PORT & 0xFF) << 8) | ((SERVER_PORT >> 8) & 0xFF));  // htons

   uchar ip_bytes[];
   StringToBytes("127.0.0.1", ip_bytes);
   addr.sin_addr = inet_addr(ip_bytes);

   for (int i = 0; i < 8; i++) addr.sin_zero[i] = 0;

   // Serialize and bind
   uchar addr_bytes[];
   SerializeSockaddr(addr, addr_bytes);
   if (bind(g_server_socket, addr_bytes, 16) == SOCKET_ERROR) {
      Print("[AURUM] Failed to bind port ", SERVER_PORT);
      closesocket(g_server_socket);
      return INIT_FAILED;
   }

   // Listen
   if (listen(g_server_socket, SOMAXCONN) == SOCKET_ERROR) {
      Print("[AURUM] Failed to listen");
      closesocket(g_server_socket);
      return INIT_FAILED;
   }

   EventSetMillisecondTimer(TIMER_MS);
   Print("[AURUM] Server listening on 127.0.0.1:", SERVER_PORT);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   if (g_client_socket != INVALID_SOCKET) closesocket(g_client_socket);
   if (g_server_socket != INVALID_SOCKET) closesocket(g_server_socket);
   Print("[AURUM] Server stopped");
}

//+------------------------------------------------------------------+
void OnTimer()
{
   // Accept new connection if no client connected
   if (g_client_socket == INVALID_SOCKET) {
      uchar addr_bytes[16];
      int addrlen = 16;
      int new_socket = accept(g_server_socket, addr_bytes, addrlen);
      if (new_socket != INVALID_SOCKET) {
         uint nb = 1;
         ioctlsocket(new_socket, FIONBIO, nb);
         g_client_socket = new_socket;
         Print("[AURUM] Client connected");
      }
      return;
   }

   // Receive data from client
   uchar buf[1024];
   int bytes = recv(g_client_socket, buf, sizeof(buf), 0);

   if (bytes == SOCKET_ERROR) {
      if (WSAGetLastError() == WSAEWOULDBLOCK) return; // no data yet, not a disconnect
      closesocket(g_client_socket);
      g_client_socket = INVALID_SOCKET;
      g_recv_buffer = "";
      Print("[AURUM] Client disconnected");
      return;
   }
   if (bytes == 0) {
      closesocket(g_client_socket);
      g_client_socket = INVALID_SOCKET;
      g_recv_buffer = "";
      Print("[AURUM] Client disconnected");
      return;
   }

   // Add received data to buffer
   g_recv_buffer += CharArrayToString(buf, 0, bytes);

   // Check for complete command (ends with \n)
   int newline_pos = StringFind(g_recv_buffer, "\n");
   if (newline_pos >= 0) {
      string command = StringSubstr(g_recv_buffer, 0, newline_pos);
      StringTrimRight(command);
      g_recv_buffer = StringSubstr(g_recv_buffer, newline_pos + 1);

      // Process command
      string response = ProcessCommand(command);

      // Send response
      uchar response_buf[];
      StringToCharArray(response + "\n", response_buf);
      send(g_client_socket, response_buf, StringLen(response) + 1, 0);
   }
}

//+------------------------------------------------------------------+
string ProcessCommand(string raw)
{
   string parts[];
   int n = StringSplit(raw, '|', parts);
   if (n < 1) return "ERROR|empty_command";

   string cmd = parts[0];

   //--- PING
   if (cmd == "PING") return "PONG";

   //--- STATUS (count open orders)
   if (cmd == "STATUS") {
      int count = 0;
      for (int i = OrdersTotal() - 1; i >= 0; i--) {
         if (OrderSelect(i, SELECT_BY_POS)) {
            if (OrderMagicNumber() == MAGIC_NUMBER) count++;
         }
      }
      return "OK|" + IntegerToString(count);
   }

   //--- BUY / SELL
   if (cmd == "BUY" || cmd == "SELL") {
      if (n < 5) return "ERROR|missing_params";
      string sym  = parts[1];
      double lots = StringToDouble(parts[2]);
      double sl   = StringToDouble(parts[3]);
      double tp   = StringToDouble(parts[4]);
      int op      = (cmd == "BUY") ? OP_BUY : OP_SELL;

      double price = (op == OP_BUY) ? Ask : Bid;
      if (price <= 0) return "ERROR|invalid_price";

      int ticket  = OrderSend(sym, op, lots, price, 3, sl, tp, "AURUM", MAGIC_NUMBER, 0, clrNONE);
      if (ticket < 0) {
         return "ERROR|ordersend_failed|" + IntegerToString(GetLastError());
      }
      return "OK|" + IntegerToString(ticket);
   }

   //--- CLOSE
   if (cmd == "CLOSE") {
      if (n < 2) return "ERROR|missing_ticket";
      int ticket = (int)StringToInteger(parts[1]);
      if (!OrderSelect(ticket, SELECT_BY_TICKET)) {
         return "ERROR|ticket_not_found";
      }
      double price = (OrderType() == OP_BUY) ? Bid : Ask;
      if (!OrderClose(ticket, OrderLots(), price, 3, clrNONE)) {
         return "ERROR|close_failed|" + IntegerToString(GetLastError());
      }
      return "OK|closed";
   }

   //--- MODIFY (SL/TP)
   if (cmd == "MODIFY") {
      if (n < 4) return "ERROR|missing_params";
      int ticket = (int)StringToInteger(parts[1]);
      double sl  = StringToDouble(parts[2]);
      double tp  = StringToDouble(parts[3]);
      if (!OrderSelect(ticket, SELECT_BY_TICKET)) {
         return "ERROR|ticket_not_found";
      }
      if (!OrderModify(ticket, OrderOpenPrice(), sl, tp, 0, clrNONE)) {
         return "ERROR|modify_failed|" + IntegerToString(GetLastError());
      }
      return "OK|modified";
   }

   //--- TIMEFRAME
   if (cmd == "TIMEFRAME") {
      if (n < 3) return "ERROR|missing_params";
      string sym = parts[1];
      string tf_str = parts[2];
      int period = PeriodFromString(tf_str);
      if (period == 0) return "ERROR|unknown_period";
      ChartSetSymbolPeriod(0, sym, period);
      return "OK|timeframe_sent";
   }

   //--- GET_POSITIONS
   if (cmd == "GET_POSITIONS") {
      string result = "";
      int count = 0;
      for (int i = OrdersTotal() - 1; i >= 0; i--) {
         if (!OrderSelect(i, SELECT_BY_POS)) continue;
         if (OrderMagicNumber() != MAGIC_NUMBER) continue;
         if (OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
         string type_str = (OrderType() == OP_BUY) ? "BUY" : "SELL";
         string pos = IntegerToString(OrderTicket()) + "," +
                      type_str + "," +
                      OrderSymbol() + "," +
                      DoubleToString(OrderLots(), 2) + "," +
                      DoubleToString(OrderOpenPrice(), 5) + "," +
                      DoubleToString(OrderStopLoss(), 5) + "," +
                      DoubleToString(OrderTakeProfit(), 5) + "," +
                      DoubleToString(OrderProfit(), 2);
         if (count > 0) result += ";";
         result += pos;
         count++;
      }
      return "OK|" + result;
   }

   //--- GET_ACCOUNT
   if (cmd == "GET_ACCOUNT") {
      string result = DoubleToString(AccountBalance(), 2) + "," +
                      DoubleToString(AccountEquity(), 2) + "," +
                      DoubleToString(AccountFreeMargin(), 2) + "," +
                      AccountCurrency();
      return "OK|" + result;
   }

   //--- GET_PRICE
   if (cmd == "GET_PRICE") {
      if (n < 2) return "ERROR|missing_symbol";
      string sym = parts[1];
      double bid    = MarketInfo(sym, MODE_BID);
      double ask    = MarketInfo(sym, MODE_ASK);
      double spread = ask - bid;
      string result = DoubleToString(bid, 5) + "," +
                      DoubleToString(ask, 5) + "," +
                      DoubleToString(spread, 5);
      return "OK|" + result;
   }

   //--- GET_TIME
   if (cmd == "GET_TIME") {
      datetime t = TimeCurrent();
      return "OK|" + TimeToString(t, TIME_DATE|TIME_MINUTES|TIME_SECONDS);
   }

   return "ERROR|unknown_command";
}

//+------------------------------------------------------------------+
int PeriodFromString(string s)
{
   if (s == "M1")  return PERIOD_M1;
   if (s == "M5")  return PERIOD_M5;
   if (s == "M15") return PERIOD_M15;
   if (s == "M30") return PERIOD_M30;
   if (s == "H1")  return PERIOD_H1;
   if (s == "H4")  return PERIOD_H4;
   if (s == "D1")  return PERIOD_D1;
   if (s == "W1")  return PERIOD_W1;
   if (s == "MN1") return PERIOD_MN1;
   return 0;
}

void OnTick() { }
