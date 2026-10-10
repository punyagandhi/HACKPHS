import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import {afterEach,describe,it,expect,vi} from 'vitest';
import App from '../src/App';
import {facts} from '../src/content/facts';
import {useSim} from '../src/sim/store';
vi.mock('../src/three/Scene',()=>({default:()=>null}));
afterEach(()=>{cleanup();useSim.getState().reset()});
const normalize=(s:string)=>s.toLowerCase().replace(/[–—]/g,'-').replace(/[‘’]/g,"'").replace(/[“”]/g,'"').replace(/\s+/g,' ').trim();
describe('source and simulation',()=>{it('renders every complete source line in order',()=>{const {container}=render(<App/>);const text=normalize(container.textContent||'');Object.values(facts).forEach(f=>expect(text).toContain(normalize(f.text)))});it('steps through four phases, fires alert and resets',()=>{render(<App/>);for(let i=0;i<4;i++)fireEvent.click(screen.getByRole('button',{name:/^Step/}));expect(useSim.getState().step).toBe(4);fireEvent.click(screen.getByRole('button',{name:'Simulate head-nod'}));expect(screen.getByRole('alert').textContent).toContain('Buzzer alert');fireEvent.click(screen.getByRole('button',{name:'Reset'}));expect(useSim.getState().step).toBe(0);expect(useSim.getState().alert).toBe(false)});it('keeps sound off and supports effects and checklist',()=>{render(<App/>);expect(screen.getByRole('button',{name:'Sound off'})).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Optimize order Off'}));expect(screen.getByRole('button',{name:'Optimize order On'})).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Effects: Full'}));expect(document.documentElement.dataset.effects).toBe('lite')})});
