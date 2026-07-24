(function(){
  function parseData(element, name){
    try{return JSON.parse(element.dataset[name] || "[]");}catch(error){return [];}
  }

  var chart=document.getElementById("crmClientChart");
  if(chart){
    var labels=parseData(chart,"labels");
    var values=parseData(chart,"values").map(function(value){return Number(value)||0;});
    var max=Math.max.apply(null,values.concat([1]));
    chart.innerHTML="";

    labels.forEach(function(label,index){
      var value=values[index]||0;
      var height=Math.max(value===0?3:8,Math.round((value/max)*100));
      var column=document.createElement("div");
      column.className="crm-chart-column";
      column.innerHTML='<span class="crm-chart-value">'+value+'</span><div class="crm-chart-bar-wrap"><span class="crm-chart-bar"></span></div><span class="crm-chart-label">'+label+'</span>';
      chart.appendChild(column);
      requestAnimationFrame(function(){column.querySelector(".crm-chart-bar").style.height=height+"%";});
    });
  }

  document.querySelectorAll(".crm-progress span[data-progress]").forEach(function(bar){
    var value=Math.max(0,Math.min(100,Number(bar.dataset.progress)||0));
    requestAnimationFrame(function(){bar.style.width=value+"%";});
  });
})();
