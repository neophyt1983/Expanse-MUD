(() => {
  const song=new Audio(),effect=new Audio(),rumble=new Audio();
  let revision=0, effectRev=0, thunderRev=0, current='', effects=0;
  function play(audio){audio.play().catch(()=>{});}
  const api={
    mix(path,transpose,musicVolume,effectsVolume) {
      song.volume=musicVolume;effects=effectsVolume;
      rumble.volume=effect.volume=effects;
      if(!effects){effectRev++;thunderRev++;effect.pause();rumble.pause();}
      song.preservesPitch=false;song.playbackRate=Math.pow(2,transpose/12);
      if(!musicVolume||!path){revision++;current='';song.pause();return;}
      if(path===current){if(song.paused&&song.getAttribute('src'))play(song);return;}
      const update=++revision;current=path;song.pause();song.removeAttribute('src');
      window.ExpanseAssets.get(path).then(asset=>{
        if(update!==revision||!asset)return;
        song.src=asset.url;song.loop=true;play(song);
      });
    },
    async cue(path) {
      const update=++effectRev;
      if(!effects||!path)return;
      const asset=await window.ExpanseAssets.get(path);
      if(!asset||update!==effectRev||!effects)return;
      effect.src=asset.url;effect.volume=effects;play(effect);
    },
    async thunder(path) {
      const update=++thunderRev;
      if(!effects||!path){rumble.pause();return;}
      const asset=await window.ExpanseAssets.get(path);
      if(!asset||update!==thunderRev||!effects)return;
      rumble.src=asset.url;rumble.volume=effects;play(rumble);
    },
    test(volume) {
      if(!volume)return;
      const ctx=new AudioContext(),tone=ctx.createOscillator(),amp=ctx.createGain();
      amp.gain.value=volume*.15;tone.connect(amp);amp.connect(ctx.destination);
      tone.start();tone.stop(ctx.currentTime+.23);tone.onended=()=>ctx.close();
    }
  };
  window.addEventListener('expanse:world-assets',()=>api.mix(null,0,0,0));
  window.ExpanseWorldAudio=api;
})();
