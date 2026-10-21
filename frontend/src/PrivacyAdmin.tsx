import { useState, type FormEvent } from 'react';
import useSWR from 'swr';
import { Check, ChevronRight, ClipboardCheck, RefreshCw } from 'lucide-react';
import { patch } from './api';
import { POLL_INTERVAL } from './config';
import type { List } from './types';
import { Empty, ErrorBox, Loading, Notice, Panel, useDate } from './ui';
interface PrivacyRequest {
  id: string;
  user_id: string;
  kind: 'access' | 'rectification' | 'cancellation' | 'opposition';
  status: 'pending' | 'processing' | 'completed' | 'rejected';
  message: string;
  created_at: string;
}
const kindLabels = { access: 'Acceso', rectification: 'Rectificación', cancellation: 'Cancelación', opposition: 'Oposición' };
const stateLabels = { pending: 'Pendiente', processing: 'En atención', completed: 'Atendida', rejected: 'Rechazada' };
export function PrivacyAdmin() {
  const { data, error, isLoading, mutate } = useSWR<List<PrivacyRequest>>('/privacy/requests', { refreshInterval: POLL_INTERVAL });
  const date = useDate();
  const [selected, setSelected] = useState<PrivacyRequest | null>(null);
  const [status, setStatus] = useState<'processing' | 'completed' | 'rejected'>('processing');
  const [note, setNote] = useState('');
  const [erase, setErase] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const [notice, setNotice] = useState('');
  function open(request: PrivacyRequest) {
    setSelected(request);
    setStatus('processing');
    setNote('');
    setErase(false);
    setActionError(null);
    setNotice('');
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    setActionError(null);
    try {
      await patch(`/privacy/requests/${selected.id}`, {
        status,
        note,
        erase_evaluations: erase && selected.kind === 'cancellation' && status === 'completed',
      });
      await mutate();
      setSelected(null);
      setNotice('Gestión registrada. La respuesta administrativa queda protegida y la acción se registra en auditoría.');
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  }
  const closed = selected?.status === 'completed' || selected?.status === 'rejected';
  return <section className="privacy-admin" aria-label="Administración de solicitudes ARCO">
    <Panel title="Gestión de solicitudes ARCO" subtitle="Área administrativa · Revisa, documenta y atiende las peticiones de los usuarios" action={<button className="icon-button" aria-label="Actualizar solicitudes ARCO" onClick={() => void mutate()}><RefreshCw size={16}/></button>}>
      <ErrorBox error={error || actionError}/>
      {notice && <Notice kind="success">{notice}</Notice>}
      {isLoading ? <Loading/> : data?.items.length ? <div className="table-scroll"><table><thead><tr><th>Solicitud</th><th>Cuenta</th><th>Estado</th><th>Recibida</th><th/></tr></thead><tbody>{data.items.map(request => <tr key={request.id} className={selected?.id === request.id ? 'selected-row' : ''}><td><button className="table-link" onClick={() => open(request)}>{kindLabels[request.kind]}</button><span className="url-preview">#{request.id.slice(0, 8)}</span></td><td><code>{request.user_id.slice(0, 8)}</code></td><td><span className={`status status-${request.status}`}><i/>{stateLabels[request.status]}</span></td><td className="muted nowrap">{date(request.created_at)}</td><td><button className="icon-button small" aria-label={`Revisar solicitud ${request.id.slice(0, 8)}`} onClick={() => open(request)}><ChevronRight size={16}/></button></td></tr>)}</tbody></table></div> : <Empty title="Sin solicitudes ARCO">Las solicitudes de los usuarios aparecerán aquí para su atención.</Empty>}
    </Panel>
    {selected && <Panel title={`${kindLabels[selected.kind]} · #${selected.id.slice(0, 8)}`} action={<button className="text-button" onClick={() => setSelected(null)}>Cerrar detalle</button>}>
      <div className="panel-padded"><div className="privacy-request-message"><ClipboardCheck size={18}/><p>{selected.message}</p></div>
        {closed ? <Notice>Esta solicitud ya fue resuelta: {stateLabels[selected.status]}. Su respuesta se conserva en el detalle.</Notice> : <form className="privacy-process-form" onSubmit={save}>
          <label>Estado de atención<select aria-label="Estado de atención" value={status} onChange={event => { setStatus(event.target.value as typeof status); setErase(false); }}><option value="processing">En atención</option><option value="completed">Atendida</option><option value="rejected">Rechazada con sustento</option></select></label>
          <label>Respuesta administrativa<textarea value={note} onChange={event => setNote(event.target.value)} rows={4} required maxLength={1000} placeholder="Documenta la verificación, las acciones realizadas y la respuesta al titular…"/><span className="form-hint">Registra el sustento de la decisión. Máximo 1000 caracteres.</span></label>
          {selected.kind === 'cancellation' && status === 'completed' && <div className="consent-box destructive-consent"><label className="checkbox-label"><input type="checkbox" checked={erase} onChange={event => setErase(event.target.checked)}/><span><strong>Ejecutar la cancelación de los datos de esta cuenta</strong><small>Acción irreversible: elimina sus evaluaciones y reportes afectados, revoca sus sesiones, desactiva y anonimiza su cuenta. Verifica la identidad y el alcance antes de autorizarla. No se puede ejecutar sobre una cuenta administrativa activa.</small></span></label></div>}
          <button className="button primary" disabled={busy}><Check size={16}/>{busy ? 'Guardando…' : 'Registrar atención'}</button>
        </form>}
      </div>
    </Panel>}
  </section>;
}
