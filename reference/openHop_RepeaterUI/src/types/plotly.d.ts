declare module 'plotly.js-dist-min' {
  interface PlotlyData {
    z?: number[][] | number[][][];
    x?: number[] | number[][];
    y?: number[] | number[][];
    type?: string;
    colorscale?: Array<[number, string]> | string;
    showscale?: boolean;
    colorbar?: Record<string, unknown>;
    hoverongaps?: boolean;
    hovertemplate?: string;
    text?: string[][] | string[][][];
  }

  interface PlotlyLayout {
    title?: Record<string, unknown>;
    xaxis?: Record<string, unknown>;
    yaxis?: Record<string, unknown>;
    plot_bgcolor?: string;
    paper_bgcolor?: string;
    font?: Record<string, unknown>;
    margin?: Record<string, unknown>;
  }

  interface PlotlyConfig {
    responsive?: boolean;
    displayModeBar?: boolean;
    modeBarButtonsToRemove?: string[];
    displaylogo?: boolean;
    toImageButtonOptions?: Record<string, unknown>;
  }

  const Plotly: {
    newPlot: (
      id: string | HTMLElement,
      data: PlotlyData[],
      layout: PlotlyLayout,
      config?: PlotlyConfig,
    ) => Promise<void>;
    restyle: (
      id: string | HTMLElement,
      update: Partial<PlotlyData>,
      traces?: number[],
    ) => Promise<void>;
    purge: (id: string | HTMLElement) => void;
    Plots?: {
      resize: (id: string | HTMLElement) => void;
    };
  };

  export default Plotly;
}
