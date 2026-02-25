import React, { useRef, useEffect, useCallback, useMemo } from "react";
import cytoscape, { type Core, type EventObject } from "cytoscape";
import type { GraphSnapshot, GraphNode, EdgeType, SelectedNode } from "../types";
import { EDGE_COLORS, SPEAKER_COLORS } from "../types";

interface GraphViewProps {
  graph: GraphSnapshot | null;
  onNodeSelect: (selected: SelectedNode | null) => void;
  highlightTimestamp?: number | null;
  maxTimestamp?: number | null;
}

// Get color based on claim type (defined outside component to avoid closure issues)
const getClaimTypeColor = (claimType: string): string => {
  switch (claimType) {
    case "conclusion":
      return "#f59e0b";
    case "rebuttal":
      return "#ef4444";
    case "concession":
      return "#10b981";
    case "premise":
      return "#3b82f6";
    default:
      return "#6b7280";
  }
};

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

/**
 * Interactive argument graph visualization using Cytoscape.js.
 * Nodes = claims, edges = argumentative relations.
 * Color-coded by speaker (nodes) and relation type (edges).
 */
export default function GraphView({
  graph,
  onNodeSelect,
  highlightTimestamp,
  maxTimestamp,
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

  // Get border style for fallacies
  const getNodeBorder = useCallback((node: GraphNode) => {
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
  }, []);

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
          full_text: nodeData.fullText,
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

    // Tooltip on hover — show full text in a custom floating tooltip
    cy.on("mouseover", "node", (evt: EventObject) => {
      const nodeData = evt.target.data();
      const fullText = nodeData.fullText || nodeData.fullLabel || "";
      const speaker = (nodeData.speaker || "").replace("SPEAKER_", "Speaker ");
      const ts = `${(nodeData.timestampStart || 0).toFixed(1)}s`;
      const type = nodeData.claimType || "premise";
      const speakerColor = getSpeakerColor(nodeData.speaker);
      const typeColor = getClaimTypeColor(type);
      
      // Find or create tooltip
      let tooltip = document.getElementById("graph-tooltip");
      if (!tooltip) {
        tooltip = document.createElement("div");
        tooltip.id = "graph-tooltip";
        tooltip.className = "fixed z-50 bg-gray-900 border border-gray-700 rounded-lg shadow-xl p-3 pointer-events-none";
        tooltip.style.display = "none";
        document.body.appendChild(tooltip);
      }
      
      tooltip.innerHTML = `
        <div class="text-xs font-semibold mb-1" style="color: ${speakerColor}">
          ${speaker} <span class="text-gray-500">@ ${ts}</span>
        </div>
        <div class="text-xs px-2 py-1 rounded inline-block mb-2" style="background-color: ${typeColor}22; color: ${typeColor}">
          ${type}
        </div>
        <div class="text-sm max-w-xs whitespace-pre-wrap text-gray-200">${fullText}</div>
      `;
      tooltip.style.display = "block";
      
      // Position tooltip near the node
      const pos = evt.target.renderedPosition();
      const containerRect = containerRef.current?.getBoundingClientRect();
      if (containerRect) {
        tooltip.style.left = `${containerRect.left + pos.x + 20}px`;
        tooltip.style.top = `${containerRect.top + pos.y - 10}px`;
      }
    });

    cy.on("mouseout", "node", () => {
      const tooltip = document.getElementById("graph-tooltip");
      if (tooltip) {
        tooltip.style.display = "none";
      }
    });
    
    // Move tooltip with mouse over nodes
    cy.on("mousemove", "node", (evt: EventObject) => {
      const tooltip = document.getElementById("graph-tooltip");
      if (tooltip && tooltip.style.display !== "none") {
        const pos = evt.target.renderedPosition();
        const containerRect = containerRef.current?.getBoundingClientRect();
        if (containerRect) {
          tooltip.style.left = `${containerRect.left + pos.x + 20}px`;
          tooltip.style.top = `${containerRect.top + pos.y - 10}px`;
        }
      }
    });

    cyRef.current = cy;

    return () => {
      // Cleanup tooltip
      const tooltip = document.getElementById("graph-tooltip");
      if (tooltip) {
        tooltip.remove();
      }
      cy.destroy();
    };
  }, [onNodeSelect, getSpeakerColor]);

  // Track previous node count to detect incremental updates
  const prevNodeCountRef = useRef(0);

  // Update graph data — supports incremental updates
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !graph) return;

    const existingNodeIds = new Set(cy.nodes().map((n) => n.id()));
    const existingEdgeIds = new Set(cy.edges().map((e) => e.id()));
    const newNodeIds = new Set(graph.nodes.map((n) => n.id));
    const newEdgeIds = new Set(graph.edges.map((e) => `${e.source}-${e.target}`));

    // Check if this is an incremental update (nodes only added, not replaced)
    const isIncremental =
      prevNodeCountRef.current > 0 &&
      graph.nodes.length >= prevNodeCountRef.current &&
      [...existingNodeIds].every((id) => newNodeIds.has(id));

    if (!isIncremental) {
      // Full rebuild: remove all and re-add
      cy.elements().remove();
    } else {
      // Remove nodes/edges that no longer exist (rare but possible)
      cy.nodes().forEach((n) => {
        if (!newNodeIds.has(n.id())) n.remove();
      });
      cy.edges().forEach((e) => {
        if (!newEdgeIds.has(e.id())) e.remove();
      });
    }

    const newElements: cytoscape.ElementDefinition[] = [];

    graph.nodes.forEach((node, i) => {
      const border = getNodeBorder(node);
      const truncatedLabel =
        node.label.length > 40
          ? node.label.substring(0, 37) + "..."
          : node.label;

      const nodeData = {
        id: node.id,
        label: truncatedLabel,
        fullLabel: node.label,
        fullText: node.full_text || node.label,
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
      };

      if (isIncremental && existingNodeIds.has(node.id)) {
        // Update existing node data (e.g. fallacies, factcheck may have changed)
        const cyNode = cy.getElementById(node.id);
        cyNode.data(nodeData);
      } else {
        // New node
        newElements.push({
          group: "nodes",
          data: nodeData,
          position: {
            x: 150 + (i % 4) * 200 + Math.random() * 50,
            y: 100 + Math.floor(i / 4) * 150 + Math.random() * 50,
          },
        });
      }
    });

    graph.edges.forEach((edge) => {
      const edgeId = `${edge.source}-${edge.target}`;
      if (isIncremental && existingEdgeIds.has(edgeId)) {
        // Edge already exists, skip
        return;
      }
      newElements.push({
        group: "edges",
        data: {
          id: edgeId,
          source: edge.source,
          target: edge.target,
          color: EDGE_COLORS[edge.relation_type as EdgeType] || "#6b7280",
          relationType: edge.relation_type,
        },
      });
    });

    if (newElements.length > 0) {
      cy.add(newElements);
    }

    prevNodeCountRef.current = graph.nodes.length;

    // Run layout — use shorter animation for incremental updates
    cy.layout({
      name: "cose",
      animate: true,
      animationDuration: isIncremental ? 300 : 500,
      nodeRepulsion: () => 8000,
      idealEdgeLength: () => 150,
      gravity: 0.3,
      padding: 50,
    } as any).run();
  }, [graph, getSpeakerColor, getNodeBorder]);

  // Filter nodes by maxTimestamp (video-review mode: progressive graph reveal)
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !graph) return;

    if (maxTimestamp == null) {
      // No filtering — show everything
      cy.nodes().forEach((n) => n.style("display", "element"));
      cy.edges().forEach((e) => e.style("display", "element"));
      return;
    }

    // Build set of visible node IDs based on timestamp
    const visibleNodeIds = new Set<string>();
    graph.nodes.forEach((node) => {
      if (node.timestamp_start <= maxTimestamp) {
        visibleNodeIds.add(node.id);
      }
    });

    // Toggle node visibility
    cy.nodes().forEach((cyNode) => {
      cyNode.style("display", visibleNodeIds.has(cyNode.id()) ? "element" : "none");
    });

    // Toggle edge visibility — both endpoints must be visible
    cy.edges().forEach((cyEdge) => {
      const srcVisible = visibleNodeIds.has(cyEdge.source().id());
      const tgtVisible = visibleNodeIds.has(cyEdge.target().id());
      cyEdge.style("display", srcVisible && tgtVisible ? "element" : "none");
    });
  }, [maxTimestamp, graph]);

  // Highlight node at current audio timestamp
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !graph || highlightTimestamp == null) return;

    cy.elements().removeClass("highlighted dimmed");

    // Only consider visible nodes for highlighting
    const matchingNode = graph.nodes.find(
      (n) =>
        (maxTimestamp == null || n.timestamp_start <= maxTimestamp) &&
        highlightTimestamp >= n.timestamp_start &&
        highlightTimestamp <= n.timestamp_end
    );

    if (matchingNode) {
      const cyNode = cy.getElementById(matchingNode.id);
      if (cyNode.length > 0 && cyNode.style("display") !== "none") {
        cyNode.addClass("highlighted");
        // Dim other visible nodes
        cy.nodes()
          .filter((n) => n.style("display") !== "none")
          .not(cyNode)
          .addClass("dimmed");
        cy.edges()
          .filter((e) => e.style("display") !== "none")
          .not(cyNode.connectedEdges())
          .addClass("dimmed");
      }
    }
  }, [highlightTimestamp, maxTimestamp, graph]);

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
            <p className="text-sm">Upload audio to see the argument graph</p>
          </div>
        </div>
      )}
    </div>
  );
}
