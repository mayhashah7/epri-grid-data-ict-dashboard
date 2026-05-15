import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { Substation } from '../lib/api';

const STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

export function GridMap({ substations }: { substations: Substation[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<Map<string, maplibregl.Marker>>(new Map());

  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    mapRef.current = new maplibregl.Map({
      container: ref.current,
      style: STYLE,
      center: [-97.74, 30.27],
      zoom: 9,
      attributionControl: false,
    });
    mapRef.current.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !substations.length) return;
    const apply = () => {
      const seen = new Set<string>();
      for (const s of substations) {
        seen.add(s.substation_id);
        const offlineFrac = s.meter_count > 0 ? s.offline_count / s.meter_count : 0;
        const color = offlineFrac > 0.10 ? '#ef4444' : offlineFrac > 0.02 ? '#f59e0b' : '#10b981';
        const size = 18 + Math.min(28, Math.sqrt(s.meter_count) * 0.6);
        let marker = markersRef.current.get(s.substation_id);
        if (!marker) {
          const el = document.createElement('div');
          el.style.cssText = `width:${size}px;height:${size}px;border-radius:50%;background:${color};box-shadow:0 0 14px ${color},0 0 0 2px rgba(255,255,255,.25) inset;cursor:pointer;display:flex;align-items:center;justify-content:center;color:white;font-size:10px;font-weight:600;font-family:JetBrains Mono,monospace;`;
          el.textContent = s.name.replace('Substation ', 'S');
          el.title = `${s.name}\n${s.meter_count} meters · ${s.offline_count} offline · ${s.total_kw.toFixed(1)} kW`;
          marker = new maplibregl.Marker({ element: el }).setLngLat([s.lon, s.lat]).addTo(map);
          markersRef.current.set(s.substation_id, marker);
        } else {
          (marker.getElement() as HTMLDivElement).style.background = color;
          (marker.getElement() as HTMLDivElement).style.boxShadow = `0 0 14px ${color},0 0 0 2px rgba(255,255,255,.25) inset`;
          marker.getElement().title = `${s.name}\n${s.meter_count} meters · ${s.offline_count} offline · ${s.total_kw.toFixed(1)} kW`;
        }
      }
      for (const [id, m] of markersRef.current.entries()) {
        if (!seen.has(id)) { m.remove(); markersRef.current.delete(id); }
      }
    };
    if (map.isStyleLoaded()) apply();
    else map.on('load', apply);
  }, [substations]);

  return <div ref={ref} className="w-full h-full" />;
}
