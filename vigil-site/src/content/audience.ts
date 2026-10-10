import { facts } from './facts';
export const audience = ["A1", "A2", "A3", "A4"].map(id => facts[id as keyof typeof facts]);
