(function(){
  function iniciar(campo){
    let centavos=(campo.value||'0,00').replace(/\D/g,'').replace(/^0+/,'')||'0';
    function mostrar(){const s=centavos.padStart(3,'0');campo.value=s.slice(0,-2).replace(/\B(?=(\d{3})+(?!\d))/g,'.')+','+s.slice(-2);}
    campo.addEventListener('keydown',e=>{if(e.ctrlKey||e.metaKey||e.altKey)return;if(/^\d$/.test(e.key)){e.preventDefault();centavos=(centavos+e.key).replace(/^0+/,'')||'0';centavos=centavos.slice(-12);mostrar();}else if(e.key==='Backspace'||e.key==='Delete'){e.preventDefault();centavos=centavos.slice(0,-1)||'0';mostrar();}else if(e.key.length===1)e.preventDefault();});
    campo.addEventListener('paste',e=>{e.preventDefault();const t=e.clipboardData.getData('text').trim();if(!/^\d+(?:[,.]\d{1,2})?$/.test(t))return;const p=t.split(/[,.]/);centavos=(p.length===2?p[0]+p[1].padEnd(2,'0'):p[0]+'00').replace(/^0+/,'').slice(-12)||'0';mostrar();});
    campo.addEventListener('input',()=>{centavos=campo.value.replace(/\D/g,'').replace(/^0+/,'').slice(-12)||'0';mostrar();});mostrar();
  }
  document.querySelectorAll('.fin-money').forEach(iniciar);
})();