import { ELEVENLABS_AGENT_ID } from '../config';
export interface VoiceIntegration { agentId: string; enabled: false; checkIn: () => Promise<never> }
export const elevenlabs: VoiceIntegration = { agentId: import.meta.env.VITE_ELEVENLABS_AGENT_ID || ELEVENLABS_AGENT_ID, enabled: false, checkIn: async () => { throw new Error('Voice integration is not enabled in this simulation.'); } };
