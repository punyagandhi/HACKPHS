import {create} from 'zustand';
export interface SimState { step:number; alert:boolean; lite:boolean; advance:()=>void; reset:()=>void; buzz:()=>void; calm:()=>void; setLite:(v:boolean)=>void }
export const useSim=create<SimState>(set=>({step:0,alert:false,lite:false,advance:()=>set(s=>({step:Math.min(4,s.step+1)})),reset:()=>set({step:0,alert:false}),buzz:()=>set({alert:true}),calm:()=>set({alert:false}),setLite:lite=>set({lite})}));
