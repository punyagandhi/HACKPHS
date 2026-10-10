import { facts } from './facts';
export const pipeline = ["P"].map(id => facts[id as keyof typeof facts]);
