import React, { useRef, useEffect, useCallback } from "react";
import cytoscape, { type Core, type EventObject } from "cytoscape";
import type { GraphSnapshot, GraphNode, EdgeType, SelectedNode } from "../types";
import { EDGE_COLORS, SPEAKER_COLORS } from "../types";

interface GraphViewProps {
  graph: GraphSnapshot | null;
  onNodeSelect: (selected: SelectedNode | null) => void;
  highlightTimestamp?: number | null;
}

/**
 * Interactive argument graph visualization using Cytoscape.js.
 * Nodes = claims, edges = argumentative relations.
 * Color-coded by speaker (nodes) and relation type (edges).
 */
export default function GraphView({
  graph,
  onNodeSelect,
  highlightTimestamp,
}: GraphViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  // Speaker → color index mapping
  const getSpeakerColor = useCallback(
    (speaker: string): string => {
      if (!graph) return SPEAKER_COLORS[0];
      const speakers = [...new Set(graph.nodes.map((n) => n.speaker))];
      const idx = speakers.indexOf(speaker);
      return SPEAKER_COLORS[idx % SPEAKER_COLORS.length];
    },
    [graph]
  );

  // Get node shape based on claim type
  const getNodeShape = (claimType: string): string => {
    switch (claimType) {
      case "conclusion":
        return "diamond";
      case "rebuttal":
        return "triangle";
      case "concession":
        return "round-rectangle";
      default:
        return "ellipse";
    }
  };

  // Get border style for fallacies
  const getNodeBorder = (node: GraphNode) => {
    if (node.fallacies.length > 0) {
      return { borderWidth: 3, borderColor: "#ef4444" };
    }
    if (node.factcheck_verdict === "refuted") {
      return { borderWidth: 3, borderColor: "#ef4444" };
    }
    if (node.factcheck_verdict === "supported") {
      return { borderWidth: 2, borderColor: "#22c55e" };
    }
    return { borderWidth: 1, borderColor: "#374151" };
  };

  // Initialize Cytoscape
  useEffect(() => {
    if (!containerRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "text-wrap": "wrap" as const,
            "text-max-width": "120px",
            "font-size": "11px",
            color: "#e5e7eb",
            "text-valign": "center" as const,
            "text-halign": "center" as const,
            "background-color": "data(bgColor)",
            shape: "data(shape)" as any,
            width: "data(size)",
            height: "data(size)",
            "border-width": "data(borderWidth)",
            "border-color": "data(borderColor)",
            "overlay-padding": "6px",
          },
        },
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "data(color)",
            "target-arrow-color": "data(color)",
            "target-arrow-shape": "triangle" as const,
            "curve-style": "bezier" as const,
            "arrow-scale": 1.2,
            opacity: 0.8,
          },
        },
        {
          selector: "node:selected",
          style: {
            "border-width": 4,
            "border-color": "#f59e0b",
            "overlay-color": "#f59e0b",
            "overlay-opacity": 0.15,
          },
        },
        {
          selector: ".highlighted",
          style: {
            "border-width": 4,
            "border-color": "#f59e0b",
            "background-opacity": 1,
          },
        },
        {
          selector: ".dimmed",
          style: {
            opacity: 0.3,
          },
        },
      ],
      layout: { name: "preset" },
      minZoom: 0.3,
      maxZoom: 3,
      wheelSensitivity: 0.3,
    });

    // Click handler
    cy.on("tap", "node", (evt: EventObject) => {
      const nodeData = evt.target.data();
      const pos = evt.target.renderedPosition();
      onNodeSelect({
        node: {
          id: nodeData.id,
          label: nodeData.fullLabel,
          speaker: nodeData.speaker,
          claim_type: nodeData.claimType,
          timestamp_start: nodeData.timestampStart,
          timestamp_end: nodeData.timestampEnd,
          confidence: nodeData.confidence,
          is_factual: nodeData.isFactual,
          factcheck_verdict: nodeData.factcheckVerdict,
          factcheck: nodeData.factcheck || null,
          fallacies: nodeData.fallacies || [],
        },
        position: { x: pos.x, y: pos.y },
      });
    });

    // Click on background to deselect
    cy.on("tap", (evt: EventObject) => {
      if (evt.target === cy) {
        onNodeSelect(null);
      }
    });

    cyRef.current = cy;

    return () => {
      cy.destroy();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Update graph data
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !graph) return;

    cy.elements().remove();

    // Add nodes
    const elements: cytoscape.ElementDefinition[] = [];

    graph.nodes.forEach((node, i) => {
      const border = getNodeBorder(node);
      const truncatedLabel =
        node.label.length > 40
          ? node.label.substring(0, 37) + "..."
          : node.label;

      elements.push({
        group: "nodes",
        data: {
          id: node.id,
          label: truncatedLabel,
          fullLabel: node.label,
          speaker: node.speaker,
          claimType: node.claim_type,
          timestampStart: node.timestamp_start,
          timestampEnd: node.timestamp_end,
          confidence: node.confidence,
          isFactual: node.is_factual,
          factcheckVerdict: node.factcheck_verdict,
          factcheck: node.factcheck,
          fallacies: node.fallacies,
          bgColor: getSpeakerColor(node.speaker),
          shape: getNodeShape(node.claim_type),
          size: node.claim_type === "conclusion" ? 70 : 55,
          borderWidth: border.borderWidth,
          borderColor: border.borderColor,
        },
        position: {
          // Arrange in a force-directed-like layout
          x: 150 + (i % 4) * 200 + Math.random() * 50,
          y: 100 + Math.floor(i / 4) * 150 + Math.random() * 50,
        },
      });
    });

    // Add edges
    graph.edges.forEach((edge) => {
      elements.push({
        group: "edges",
        data: {
          id: `${edge.source}-${edge.target}`,
          source: edge.source,
          target: edge.target,
          color: EDGE_COLORS[edge.relation_type as EdgeType] || "#6b7280",
          relationType: edge.relation_type,
        },
      });
    });

    cy.add(elements);

    // Run layout
    cy.layout({
      name: "cose",
      animate: true,
      animationDuration: 500,
      nodeRepulsion: () => 8000,
      idealEdgeLength: () => 150,
      gravity: 0.3,
      padding: 50,
    } as any).run();
  }, [graph, getSpeakerColor]);

  // Highlight node at current audio timestamp
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !graph || highlightTimestamp == null) return;

    cy.elements().removeClass("highlighted dimmed");

    const matchingNode = graph.nodes.find(
      (n) =>
        highlightTimestamp >= n.timestamp_start &&
        highlightTimestamp <= n.timestamp_end
    );

    if (matchingNode) {
      const cyNode = cy.getElementById(matchingNode.id);
      if (cyNode.length > 0) {
        cyNode.addClass("highlighted");
        // Dim other nodes
        cy.elements().not(cyNode).not(cyNode.connectedEdges()).addClass("dimmed");
      }
    }
  }, [highlightTimestamp, graph]);

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="cytoscape-container w-full h-full" />

      {/* Legend */}
      <div className="absolute bottom-3 left-3 bg-gray-900/90 backdrop-blur-sm rounded-lg p-3 text-xs space-y-1.5">
        <div className="font-semibold text-gray-300 mb-1">Relations</div>
        {Object.entries(EDGE_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-2">
            <div
              className="w-4 h-0.5 rounded"
              style={{ backgroundColor: color }}
            />
            <span className="text-gray-400 capitalize">{type}</span>
          </div>
        ))}
      </div>

      {/* Empty state */}
      {(!graph || graph.nodes.length === 0) && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center text-gray-500">
            <svg
              className="w-16 h-16 mx-auto mb-3 opacity-30"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1}
                d="M13 10V3L4 14h7v7l9-11h-7z"
              />
            </svg>
            <p className="text-sm">Upload audio or run demo to see the argument graph</p>
          </div>
        </div>
      )}
    </div>
  );
}
