import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { SWRConfig } from 'swr';
import { AnalyzePage } from './EvaluationPages';
import { post } from './api';
vi.mock('./api',()=>({post:vi.fn()}));
vi.mock('./auth',()=>({useAuth:()=>({user:{timezone:'America/Lima',role:'user'}})}));
function mount(){return render(<MemoryRouter><SWRConfig value={{provider:()=>new Map(),dedupingInterval:0}}><AnalyzePage/></SWRConfig></MemoryRouter>);}
beforeEach(()=>{ vi.mocked(post).mockReset(); });afterEach(cleanup);
describe('Analysis consent and minimization',()=>{
 it('keeps external reputation consent opt-in',async()=>{vi.mocked(post).mockResolvedValue({id:'eval-1'});mount();const consent=screen.getByRole('checkbox',{name:/Consultar reputación externa/});expect(consent).not.toBeChecked();fireEvent.change(screen.getByLabelText('URL que recibiste'),{target:{value:'https://bcp-prueba.invalid/revisar?token=secret'}});fireEvent.click(screen.getByRole('button',{name:'Analizar enlace'}));await waitFor(()=>expect(post).toHaveBeenCalledWith('/evaluations',{url:'https://bcp-prueba.invalid/revisar?token=secret',source:'manual',external_consent:false}));});
 it('sends explicit consent and clears pasted message text after extraction',async()=>{vi.mocked(post).mockResolvedValue({evaluations:[],rejected:['private-address']});mount();fireEvent.click(screen.getByRole('tab',{name:'Correo o mensaje'}));const textarea=screen.getByLabelText('Contenido del mensaje');fireEvent.change(textarea,{target:{value:'Revisa https://ejemplo.invalid'}});fireEvent.click(screen.getByRole('checkbox',{name:/Consultar reputación externa/}));fireEvent.click(screen.getByRole('button',{name:'Extraer y analizar enlaces'}));await waitFor(()=>expect(post).toHaveBeenCalledWith('/evaluations/extract',{text:'Revisa https://ejemplo.invalid',source:'email',external_consent:true}));await waitFor(()=>expect(textarea).toHaveValue(''));expect(screen.getByText(/1 enlaces no se pudieron aceptar/)).toBeVisible();});
 it('displays backend validation errors and restores submission',async()=>{vi.mocked(post).mockRejectedValue(new Error('No se admiten direcciones privadas'));mount();fireEvent.change(screen.getByLabelText('URL que recibiste'),{target:{value:'https://127.0.0.1'}});fireEvent.click(screen.getByRole('button',{name:'Analizar enlace'}));await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('No se admiten direcciones privadas'));expect(screen.getByRole('button',{name:'Analizar enlace'})).toBeEnabled();});
});
