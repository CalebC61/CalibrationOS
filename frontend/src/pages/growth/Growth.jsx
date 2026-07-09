import React from 'react';
export default function Growth(){
  const enabled = process.env.REACT_APP_GROWTH_MODULE_ENABLED === 'true';
  if(!enabled){
    return (<div className="min-h-screen bg-[#2A2E37] text-[#E8E8E8] flex items-center justify-center p-8" style={{fontFamily:'DM Sans, sans-serif'}}>
      <div className="max-w-xl text-center border border-[#404653] rounded-2xl p-10 bg-[#343843]">
        <h1 style={{fontFamily:'Saira Stencil One, sans-serif'}} className="text-4xl text-[#F97316] mb-2 tracking-wider">CALIBRATION<span className="bg-[#F97316] text-[#2A2E37] px-2 ml-2 rounded">OS</span></h1>
        <div style={{fontFamily:'Saira Stencil One, sans-serif'}} className="text-2xl mb-4">PARTNER GROWTH ENGINE</div>
        <p className="text-[#9AA0A6]">Power Connector 5+50+100 + Zeely-lite reels<br/>Module 9 – feature-flagged OFF</p>
        <div className="mt-6 text-left bg-[#2A2E37] rounded-xl p-4 text-sm" style={{fontFamily:'JetBrains Mono, monospace'}}>
          Top 5 → daily<br/>Key 50 → weekly<br/>Vital 100 → monthly<br/><br/>
          <span className="text-[#F97316]">favors_given ≥ 2 before ask</span>
        </div>
        <p className="text-xs text-[#6B7280] mt-4">GROWTH_MODULE_ENABLED=false · see docs/module9/README.md</p>
      </div>
    </div>)
  }
  return <div>Growth Grid – coming soon</div>
}
// TODO: wire /api/growth/grid – see docs/module9/README.md
