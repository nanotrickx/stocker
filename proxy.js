const http = require('http');
const net = require('net');

const BACKEND_PORT = 8000;
const FRONTEND_PORT = 5173;
const PROXY_PORT = 9000;

// Catch all uncaught errors to guarantee high availability and prevent crashes
process.on('uncaughtException', (err) => {
  console.error('Uncaught Exception caught gracefully:', err);
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled Rejection caught gracefully at:', promise, 'reason:', reason);
});

const server = http.createServer((req, res) => {
  const isApi = req.url.startsWith('/api');
  const targetPort = isApi ? BACKEND_PORT : FRONTEND_PORT;
  
  const options = {
    hostname: '127.0.0.1',
    port: targetPort,
    path: req.url,
    method: req.method,
    headers: req.headers
  };
  
  const proxyReq = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });
  
  proxyReq.on('error', (err) => {
    console.error(`Proxy Request Error for ${req.url}:`, err.message);
    if (!res.headersSent) {
      res.writeHead(502, { 'Content-Type': 'text/plain' });
      res.end('Bad Gateway');
    }
  });
  
  req.pipe(proxyReq, { end: true });
});

// Forward WebSocket / upgrade requests
server.on('upgrade', (req, socket, head) => {
  const isApi = req.url.startsWith('/api');
  const targetPort = isApi ? BACKEND_PORT : FRONTEND_PORT;
  
  const targetSocket = net.connect(targetPort, '127.0.0.1', () => {
    // Write headers
    let rawHeaders = `${req.method} ${req.url} HTTP/${req.httpVersion}\r\n`;
    for (let i = 0; i < req.rawHeaders.length; i += 2) {
      rawHeaders += `${req.rawHeaders[i]}: ${req.rawHeaders[i+1]}\r\n`;
    }
    rawHeaders += '\r\n';
    
    targetSocket.write(rawHeaders);
    targetSocket.write(head);
    
    socket.pipe(targetSocket);
    targetSocket.pipe(socket);
  });
  
  targetSocket.on('error', (err) => {
    console.error('Target socket error in upgrade proxy:', err.message);
    socket.destroy();
  });
  
  socket.on('error', (err) => {
    console.error('Client socket error in upgrade proxy:', err.message);
    targetSocket.destroy();
  });
});

server.listen(PROXY_PORT, '0.0.0.0', () => {
  console.log(`Stocker Unified Proxy listening on port ${PROXY_PORT}`);
});
