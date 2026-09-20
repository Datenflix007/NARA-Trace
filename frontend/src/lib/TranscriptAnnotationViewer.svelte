<script lang="ts">
  import { onMount } from 'svelte';
  import type { TSTextMarkerViewer } from '@datenflix/ts-text-marker-viewer';
  import { createTranscriptAnnotationDocument } from './transcript-annotations';

  export let documentId: string;
  export let title: string;
  export let text: string;
  export let source: string;
  export let terms: string[] = [];

  let viewer: TSTextMarkerViewer | undefined;
  let viewerReady = false;

  async function synchronizeViewer() {
    if (!viewer) return;

    const document = createTranscriptAnnotationDocument({
      id: documentId,
      title,
      text,
      source,
      terms
    });

    await viewer.loadText(text, document.document);
    viewer.setMode('annotations');
    viewer.setAnnotationDisplayStyle('bracket');
    viewer.setAnnotationDocument(document);
  }

  onMount(async () => {
    await import('@datenflix/ts-text-marker-viewer');
    viewerReady = true;
  });

  $: if (viewer && viewerReady) {
    void synchronizeViewer();
  }
</script>

<details class="annotation-viewer">
  <summary>Interaktive Textansicht mit Suchmarkierungen</summary>
  <p>Die Markierungen werden aus dem aktuellen Suchprofil erzeugt. Sie ändern weder OCR noch Originalquelle.</p>
  <ts-text-marker-viewer bind:this={viewer} demo-button-label="Demo ausblenden"></ts-text-marker-viewer>
</details>
