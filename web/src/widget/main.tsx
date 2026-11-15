import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/styles/index.css';
import './widget.css';
import { HostConnection, windowTransport } from './protocol';
import { WidgetApp } from './WidgetApp';

// no embedding host (the file opened on its own): say what this is instead of waiting for a handshake
const embedded = window.parent !== window;
const connection = embedded ? new HostConnection(windowTransport()) : null;

const root = document.getElementById('root');
if (!root) throw new Error('#root missing');
createRoot(root).render(
  <StrictMode>
    <WidgetApp connection={connection} />
  </StrictMode>,
);
