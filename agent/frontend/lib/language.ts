// Shared by server (layout, token route) and client code. Must not be a
// 'use client' module: server components importing a client module receive a
// reference placeholder instead of the actual values.

export type Language = 'en' | 'zh';

export const LANGUAGE_COOKIE = 'wang-lang';
