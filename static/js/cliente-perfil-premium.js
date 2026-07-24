(function(){
  document.querySelectorAll('.customer-chart-fill[data-height]').forEach(function(bar){
    var value=Math.max(0,Math.min(100,Number(bar.dataset.height||0)));
    bar.style.height=value+'%';
  });

  document.querySelectorAll('.js-whatsapp[data-phone]').forEach(function(button){
    button.addEventListener('click',function(){
      var phone=String(button.dataset.phone||'').replace(/\D/g,'');
      if(!phone){return;}
      if(phone.length<=11){phone='55'+phone;}
      window.open('https://wa.me/'+phone,'_blank','noopener,noreferrer');
    });
  });
})();
