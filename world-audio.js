(() => {
  const song=new Audio(),effect=new Audio(),rumble=new Audio();
  const mediaLeases=new Map();
  function releaseMedia(audio){
    audio.pause();audio.removeAttribute('src');audio.load?.();
    mediaLeases.get(audio)?.release?.();mediaLeases.delete(audio);
  }
  function useMedia(audio,asset){releaseMedia(audio);mediaLeases.set(audio,asset);audio.src=asset.url;}
  let revision=0, effectRev=0, thunderRev=0, current='', effects=0;
  let performanceContext=null,performanceGain=null,performanceRevision=0,performanceVolume=0;
  const performanceNodes=new Set();
  function play(audio){audio.play().catch(()=>{});}
  function number(value,min,max){return typeof value==='number'&&Number.isFinite(value)&&value>=min&&value<=max;}
  function stopPerformance(){
    performanceRevision++;
    if(performanceGain){try{performanceGain.gain.cancelScheduledValues(0);performanceGain.gain.value=0;performanceGain.disconnect();}catch{}performanceGain=null;}
    for(const row of performanceNodes){try{row.source.stop();}catch{}try{row.source.disconnect();row.gain.disconnect();}catch{}}
    performanceNodes.clear();
  }
  function scoreNotes(cue){
    const score=cue?.score,age=cue?.age_seconds??0;
    if(cue?.rendering!=='synthesized'||!number(age,0,20)||score?.version!==1||!number(score.tempo,40,240)||!Array.isArray(score.tracks)||score.tracks.length>8)return null;
    const notes=[],seconds=60/score.tempo;
    for(const track of score.tracks){
      if(!track||!['lead','response','relay','accompaniment'].includes(track.role)||!['periodic','noise'].includes(track.timbre)||!number(track.gain,0,1)||!Array.isArray(track.notes))return null;
      if(track.role!=='accompaniment'&&track.timbre!=='periodic')return null;
      if(track.role==='relay'&&(!Number.isInteger(track.participant)||track.participant<1||track.participant>3))return null;
      if(track.role==='accompaniment'&&(typeof track.instrument!=='string'||!track.instrument))return null;
      const envelope=track.envelope;
      if(!envelope||!number(envelope.attack,0,1)||!number(envelope.decay,0,2)||!number(envelope.sustain,0,1)||!number(envelope.release,0,2))return null;
      if(track.timbre==='periodic'&&(!Array.isArray(track.harmonics)||!track.harmonics.length||track.harmonics.length>16||!track.harmonics.every(v=>number(v,0,1))||!track.harmonics.some(v=>v>0)))return null;
      for(const note of track.notes){
        if(!Array.isArray(note)||note.length!==4||!Number.isInteger(note[0])||!number(note[0],24,108)||!number(note[1],0,80)||!number(note[2],Number.MIN_VALUE,80)||!number(note[3],0,1)||notes.length>=128)return null;
        const start=note[1]*seconds,duration=note[2]*seconds,end=start+duration+envelope.release;
        if(end>20+1e-8)return null;
        notes.push({track,midi:note[0],velocity:note[3],start,duration,end,age});
      }
    }
    return notes;
  }
  function noise(context){
    const buffer=context.createBuffer(1,context.sampleRate,context.sampleRate),channel=buffer.getChannelData(0);
    // A repeatable neutral noise source. Rhythm and envelope remain authored.
    let seed=19012;
    for(let i=0;i<channel.length;i++){seed=(Math.imul(seed,1664525)+1013904223)>>>0;channel[i]=seed/2147483648-1;}
    return buffer;
  }
  async function perform(cue){
    stopPerformance();const version=performanceRevision;
    const parsed=scoreNotes(cue),notes=parsed?.filter(note=>note.end>note.age&&note.velocity&&note.track.gain);
    if(!performanceVolume||!notes?.length)return false;
    try{
      const AudioContextClass=window.AudioContext||window.webkitAudioContext;
      if(!AudioContextClass)return false;
      if(!performanceContext||performanceContext.state==='closed')performanceContext=new AudioContextClass();
      const context=performanceContext;
      if(context.state!=='running')await context.resume();
      if(version!==performanceRevision||!performanceVolume)return false;
      const master=context.createGain();performanceGain=master;
      master.gain.value=performanceVolume*.35;master.connect(context.destination);
      const now=context.currentTime+.015,waves=new Map(),noiseBuffer=notes.some(n=>n.track.timbre==='noise')?noise(context):null;
      // Normalize the simultaneous authored voices without changing their mix.
      const events=notes.flatMap(n=>[[n.start,1],[n.end,-1]]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
      let voices=0,peak=1;for(const [,change] of events){voices+=change;peak=Math.max(peak,voices);}
      for(const note of notes){
        const track=note.track,envelope=track.envelope,source=track.timbre==='noise'?context.createBufferSource():context.createOscillator(),amp=context.createGain();
        if(track.timbre==='noise'){source.buffer=noiseBuffer;source.loop=true;}
        else{
          if(!waves.has(track)){const real=new Float32Array(track.harmonics.length+1),imaginary=new Float32Array(track.harmonics.length+1);imaginary.set(track.harmonics,1);waves.set(track,context.createPeriodicWave(real,imaginary));}
          source.setPeriodicWave(waves.get(track));source.frequency.value=440*Math.pow(2,(note.midi-69)/12);
        }
        const start=now+Math.max(0,note.start-note.age),elapsed=Math.max(0,note.age-note.start);
        const attack=Math.min(envelope.attack,note.duration),decay=Math.min(envelope.decay,Math.max(0,note.duration-attack));
        const gain=track.gain*note.velocity/peak,sustain=gain*envelope.sustain;
        const points=[[0,0],[attack,gain],[attack+decay,sustain],[note.duration,sustain],[note.duration+envelope.release,0]];
        // Start at the actual age of a room cue. Late packets do not restart
        // attacks or sustain a note that is already in its release phase.
        let level=0;
        for(let i=1;i<points.length;i++){
          const [left,a]=points[i-1],[right,b]=points[i];
          if(elapsed>=right){level=b;continue;}
          if(elapsed>=left){level=a+(b-a)*(elapsed-left)/(right-left);break;}
        }
        amp.gain.setValueAtTime(level,start);
        for(const [time,value] of points)if(time>elapsed)amp.gain.linearRampToValueAtTime(value,start+time-elapsed);
        source.connect(amp);amp.connect(master);
        const row={source,gain:amp};performanceNodes.add(row);
        source.onended=()=>{performanceNodes.delete(row);try{source.disconnect();amp.disconnect();}catch{}if(version===performanceRevision&&!performanceNodes.size){master.disconnect();if(performanceGain===master)performanceGain=null;}};
        source.start(start);source.stop(start+note.duration+envelope.release-elapsed+.005);
      }
      if(!performanceNodes.size){master.disconnect();performanceGain=null;return false;}
      return true;
    }catch{if(version===performanceRevision)stopPerformance();return false;}
  }
  const api={
    mix(path,transpose,musicVolume,effectsVolume) {
      song.volume=musicVolume;effects=effectsVolume;
      performanceVolume=number(musicVolume,0,1)?musicVolume:0;
      if(!performanceVolume)stopPerformance();else if(performanceGain)performanceGain.gain.value=performanceVolume*.35;
      rumble.volume=effect.volume=effects;
      if(!effects){effectRev++;thunderRev++;releaseMedia(effect);releaseMedia(rumble);}
      song.preservesPitch=false;song.playbackRate=Math.pow(2,transpose/12);
      if(!musicVolume||!path){revision++;current='';releaseMedia(song);return;}
      if(path===current){if(song.paused&&song.getAttribute('src'))play(song);return;}
      const update=++revision;current=path;releaseMedia(song);
      window.ExpanseAssets.get(path).then(asset=>{
        if(update!==revision||!asset){asset?.release?.();return;}
        useMedia(song,asset);song.loop=true;play(song);
      });
    },
    async cue(path) {
      const update=++effectRev;
      if(!effects||!path)return;
      const asset=await window.ExpanseAssets.get(path);
      if(!asset||update!==effectRev||!effects){asset?.release?.();return;}
      useMedia(effect,asset);effect.volume=effects;play(effect);
    },
    async thunder(path) {
      const update=++thunderRev;
      if(!effects||!path){releaseMedia(rumble);return;}
      const asset=await window.ExpanseAssets.get(path);
      if(!asset||update!==thunderRev||!effects){asset?.release?.();return;}
      useMedia(rumble,asset);rumble.volume=effects;play(rumble);
    },
    test(volume) {
      if(!volume)return;
      const ctx=new AudioContext(),tone=ctx.createOscillator(),amp=ctx.createGain();
      amp.gain.value=volume*.15;tone.connect(amp);amp.connect(ctx.destination);
      tone.start();tone.stop(ctx.currentTime+.23);tone.onended=()=>ctx.close();
    },
    perform,
    stopPerformance
  };
  window.addEventListener('expanse:world-assets',()=>api.mix(null,0,0,0));
  window.ExpanseWorldAudio=api;
})();
