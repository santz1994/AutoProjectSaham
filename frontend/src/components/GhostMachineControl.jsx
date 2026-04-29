import React, { useState, useEffect, useCallback } from 'react';
import ApiService from '../utils/apiService';

const S = {
  box: { background:'linear-gradient(135deg,#0f0f1a,#1a1a2e,#16213e)', borderRadius:12, padding:24, color:'#e0e0e0', fontFamily:"Inter,Segoe UI,sans-serif", minHeight:'80vh' },
  hdr: { display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:24, borderBottom:'1px solid #2a2a4a', paddingBottom:16 },
  ttl: { fontSize:24, fontWeight:700, color:'#00d4ff', margin:0 },
  sub: { fontSize:13, color:'#888', marginTop:4 },
  grid: { display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(320px,1fr))', gap:20 },
  card: { background:'rgba(255,255,255,0.04)', borderRadius:10, padding:20, border:'1px solid rgba(255,255,255,0.08)' },
  ct: { fontSize:15, fontWeight:600, color:'#00d4ff', marginBottom:12, textTransform:'uppercase', letterSpacing:0.5 },
  row: { display:'flex', justifyContent:'space-between', padding:'6px 0', borderBottom:'1px solid rgba(255,255,255,0.05)', fontSize:13 },
  sl: { color:'#aaa' },
  sv: { fontWeight:600, color:'#fff' },
  btn: (c,d) => ({ padding:'10px 24px', borderRadius:8, border:'none', background:d?'#333':c, color:'#fff', fontWeight:600, fontSize:14, cursor:d?'not-allowed':'pointer', opacity:d?0.5:1, marginRight:8 }),
  brow: { display:'flex', gap:8, marginTop:16 },
  badge: c => ({ display:'inline-block', padding:'3px 10px', borderRadius:12, fontSize:11, fontWeight:600, background:c, color:'#fff', textTransform:'uppercase' }),
  hi: { display:'flex', justifyContent:'space-between', alignItems:'center', padding:'8px 0', borderBottom:'1px solid rgba(255,255,255,0.05)', fontSize:12 },
  err: { background:'rgba(255,68,68,0.1)', border:'1px solid rgba(255,68,68,0.3)', borderRadius:8, padding:12, color:'#ff6666', fontSize:13, marginBottom:16 },
  rbtn: { background:'transparent', border:'1px solid #2a2a4a', color:'#888', padding:'6px 12px', borderRadius:6, cursor:'pointer', fontSize:12 },
};

export default function GhostMachineControl({ autoRefreshMs = 10000 }) {
  const [st, setSt] = useState(null);
  const [ag, setAg] = useState(null);
  const [am, setAm] = useState(null);
  const [hist, setHist] = useState([]);
  const [ld, setLd] = useState(true);
  const [err, setErr] = useState(null);
  const [act, setAct] = useState(null);

  const load = useCallback(async () => {
    try {
      const [r1,r2,r3,r4] = await Promise.allSettled([
        ApiService.get('/api/ghost-machine/status'),
        ApiService.get('/api/ghost-machine/anomaly-guard/status'),
        ApiService.get('/api/ghost-machine/automl/status'),
        ApiService.get('/api/ghost-machine/history?limit=10'),
      ]);
      if(r1.status==='fulfilled') setSt(r1.value);
      if(r2.status==='fulfilled') setAg(r2.value);
      if(r3.status==='fulfilled') setAm(r3.value);
      if(r4.status==='fulfilled') setHist(r4.value?.cycles||[]);
      setErr(null);
    } catch(e){ setErr(e.message); } finally { setLd(false); }
  },[]);

  useEffect(()=>{ load(); const t=setInterval(load,autoRefreshMs); return()=>clearInterval(t); },[load,autoRefreshMs]);

  const doAction = async a => { setAct(a); try{ await ApiService.post(`/api/ghost-machine/${a}`); await load(); }catch(e){ setErr(e.message);}finally{ setAct(null);} };

  const running = st?.running;
  const ss = st?.stats||{}, as = ag?.stats||{}, ms = am?.stats||{};

  if(ld) return <div style={S.box}><div style={{textAlign:'center',padding:60,color:'#888'}}>Loading Ghost Machine...</div></div>;

  return (
    <div style={S.box}>
      <div style={S.hdr}>
        <div><h1 style={S.ttl}>Ghost Machine Control</h1><p style={S.sub}>Autonomous 24/7 Trading Loop &mdash; Anomaly Guard &mdash; AutoML</p></div>
        <div style={{display:'flex',alignItems:'center',gap:12}}>
          <span style={S.badge(running?'#44cc44':'#ff6644')}>{running?'RUNNING':'STOPPED'}</span>
          <button style={S.rbtn} onClick={load}>Refresh</button>
        </div>
      </div>
      {err && <div style={S.err}>{err}</div>}
      <div style={S.brow}>
        <button style={S.btn('#44cc44',running||act)} disabled={running||!!act} onClick={()=>doAction('start')}>{act==='start'?'Starting...':'Start'}</button>
        <button style={S.btn('#ff4444',!running||act)} disabled={!running||!!act} onClick={()=>doAction('stop')}>{act==='stop'?'Stopping...':'Stop'}</button>
        <button style={S.btn('#ffaa00',!!act)} disabled={!!act} onClick={()=>doAction('cycle')}>{act==='cycle'?'Running...':'Single Cycle'}</button>
      </div>
      <div style={{marginTop:24}}>
        <div style={S.grid}>
          <div style={S.card}>
            <h3 style={S.ct}>Ghost Machine Stats</h3>
            <div style={S.row}><span style={S.sl}>Total Cycles</span><span style={S.sv}>{ss.total_cycles??0}</span></div>
            <div style={S.row}><span style={S.sl}>Trades Executed</span><span style={{...S.sv,color:'#44cc44'}}>{ss.trades_executed??0}</span></div>
            <div style={S.row}><span style={S.sl}>Trades Blocked</span><span style={{...S.sv,color:'#ff4444'}}>{ss.trades_blocked??0}</span></div>
            <div style={S.row}><span style={S.sl}>Trades Reduced</span><span style={{...S.sv,color:'#ffaa00'}}>{ss.trades_reduced??0}</span></div>
            <div style={S.row}><span style={S.sl}>Mode</span><span style={S.sv}>{st?.config?.live_mode?'LIVE':'PAPER'}</span></div>
          </div>
          <div style={S.card}>
            <h3 style={S.ct}>Anomaly Guard</h3>
            <div style={S.row}><span style={S.sl}>Status</span><span style={S.badge(ag?.active?'#44cc44':'#666')}>{ag?.active?'ACTIVE':'INACTIVE'}</span></div>
            <div style={S.row}><span style={S.sl}>Checks</span><span style={S.sv}>{as.checks??0}</span></div>
            <div style={S.row}><span style={S.sl}>Vetoes</span><span style={{...S.sv,color:'#ff4444'}}>{as.vetoes??0}</span></div>
            <div style={S.row}><span style={S.sl}>Reductions</span><span style={{...S.sv,color:'#ffaa00'}}>{as.reductions??0}</span></div>
          </div>
          <div style={S.card}>
            <h3 style={S.ct}>AutoML Pipeline</h3>
            <div style={S.row}><span style={S.sl}>Status</span><span style={S.badge(am?.active?'#44cc44':'#666')}>{am?.active?'ACTIVE':'INACTIVE'}</span></div>
            <div style={S.row}><span style={S.sl}>Total Runs</span><span style={S.sv}>{ms.total_runs??0}</span></div>
            <div style={S.row}><span style={S.sl}>Promotions</span><span style={{...S.sv,color:'#44cc44'}}>{ms.promotions??0}</span></div>
            <div style={S.row}><span style={S.sl}>Registry Models</span><span style={S.sv}>{am?.registry?.total_models??0}</span></div>
          </div>
          <div style={{...S.card,gridColumn:'span 2'}}>
            <h3 style={S.ct}>Recent Cycle History</h3>
            {hist.length===0?<div style={{color:'#666',fontSize:13,padding:12}}>No cycles yet. Start or trigger a single cycle.</div>:
            hist.map((c,i)=>(
              <div key={c.cycle_id||i} style={S.hi}>
                <span style={{fontFamily:'monospace'}}>{String(c.cycle_id||'').slice(-6)}</span>
                <span style={{fontSize:11}}>{c.timestamp?new Date(c.timestamp).toLocaleString():'-'}</span>
                <span style={{color:'#44cc44'}}>Exec:{c.total_trades_executed??0}</span>
                <span style={{color:'#ff4444'}}>Block:{c.total_trades_blocked??0}</span>
                <span>{c.execution_time_ms?`${c.execution_time_ms}ms`:'-'}</span>
                <span style={S.badge(c.error?'#ff4444':'#44cc44')}>{c.error?'ERR':'OK'}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}