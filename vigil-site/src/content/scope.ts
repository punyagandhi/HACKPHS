import { facts } from './facts';
export const scope = ["M1", "M1a", "M2", "M2a", "M2b", "M2c", "L1", "L2", "L2a", "L3", "X1", "X2"].map(id => facts[id as keyof typeof facts]);
