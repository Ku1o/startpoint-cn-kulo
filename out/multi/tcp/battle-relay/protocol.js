"use strict";
// IPC messages between the main CN process and the battle relay child.
//
// The child owns the real battle sockets after the handshake frame is seen.
// It relays Broadcast/Send frames and answers Measurement/Heartbeat locally,
// and forwards every other frame to the main process, which keeps all room,
// barrier, lease and settlement decisions.
Object.defineProperty(exports, "__esModule", { value: true });
