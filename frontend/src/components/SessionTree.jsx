import { useEffect, useMemo, useRef, useState } from 'react';
import { ReactFlow, Background, Controls, Handle, Position } from '@xyflow/react';
import { Check, Database, GitBranch, GitMerge, Pencil, Plus, Trash2, X } from 'lucide-react';

const NODE_Y_GAP = 98;
const TIMELINE_X_GAP = 178;
const CURRENT_STATE_GAP = 160;
const ROOT_GAP = 0.45;
const SESSION_START_Y_OFFSET = 0;
const OPERATION_Y_OFFSET = 6;
const OPERATION_EDGE_TYPE = 'straight';
const BRANCH_EDGE_TYPE = 'bezier';

export function operationNodeId(sessionId, operationId) {
  return `${sessionId}-${operationId}`;
}

export function sessionStartNodeId(sessionId) {
  return `${sessionId}__start`;
}

export function sessionOperations(session) {
  return (session?.operations || []).filter((op) => op.operation_type !== 'created_session');
}

export function depthFor(session, byId) {
  let depth = 0;
  let current = session;
  while (current?.parent_id) {
    depth += 1;
    current = byId.get(current.parent_id);
  }
  return depth;
}

export function buildSessionHierarchy(sessions) {
  const byId = new Map(sessions.map((s) => [s.id, s]));
  const childrenByParent = new Map(sessions.map((s) => [s.id, []]));
  const roots = [];

  sessions.forEach((session) => {
    if (session.parent_id && byId.has(session.parent_id)) {
      childrenByParent.get(session.parent_id).push(session);
    } else {
      roots.push(session);
    }
  });

  roots.sort((a, b) => a.created_time - b.created_time);
  childrenByParent.forEach((children) => children.sort((a, b) => a.created_time - b.created_time));

  return { byId, childrenByParent, roots };
}

export function operationsBeforeBranch(parent, child) {
  return sessionOperations(parent).filter((op) => op.time < child.created_time);
}

export function sourceOperationForBranch(parent, child) {
  const explicitSourceOperation = sessionOperations(parent).find((op) => op.id === child.source_operation_id);
  if (explicitSourceOperation) return explicitSourceOperation;

  const fallbackOperations = operationsBeforeBranch(parent, child);
  return fallbackOperations[fallbackOperations.length - 1] || null;
}

export function sourceOperationIndexForBranch(parent, child) {
  const sourceOperation = sourceOperationForBranch(parent, child);
  if (!sourceOperation) return 0;

  const index = sessionOperations(parent).findIndex((op) => op.id === sourceOperation.id);
  return index < 0 ? 0 : index + 1;
}

export function sessionEdgeSourceNodeId(session, byId) {
  if (!session.parent_id) return null;
  const parent = byId.get(session.parent_id);
  if (!parent) return session.parent_id;

  const sourceOperation = sourceOperationForBranch(parent, session);
  if (sourceOperation) return operationNodeId(parent.id, sourceOperation.id);
  return sessionOperations(parent).length > 0 ? sessionStartNodeId(parent.id) : parent.id;
}

export function sessionEdgeTargetNodeId(session) {
  return sessionOperations(session).length > 0 ? sessionStartNodeId(session.id) : session.id;
}

export function childBranchesFromFinalOperation(session, childrenByParent) {
  const operations = sessionOperations(session);
  if (operations.length === 0) return [];

  const finalOperation = operations[operations.length - 1];
  return (childrenByParent.get(session.id) || []).filter((child) => {
    const sourceOperation = sourceOperationForBranch(session, child);
    return sourceOperation?.id === finalOperation.id;
  });
}

export function shouldCollapseCurrentSessionNode(session, activeSessionId, childrenByParent) {
  if (session.id === activeSessionId) return false;
  if (sessionOperations(session).length === 0) return false;
  return childBranchesFromFinalOperation(session, childrenByParent).length > 0;
}

export function timelineTimes(sessions) {
  return Array.from(
    new Set(
      sessions.flatMap((session) => [
        session.created_time,
        ...sessionOperations(session).map((op) => op.time),
      ])
    )
  ).sort((a, b) => a - b);
}

export function buildTimelineIndex(sessions) {
  return new Map(timelineTimes(sessions).map((time, index) => [time, index]));
}

export function timelineXForTime(time, timelineIndex) {
  const slot = timelineIndex.get(time);
  return (slot ?? 0) * TIMELINE_X_GAP;
}

export function eventTimeForSessionStart(session) {
  return session.created_time;
}

export function eventTimeForOperation(operation) {
  return operation.time;
}

export function latestSessionEventTime(session) {
  const operations = sessionOperations(session);
  return operations.length > 0 ? operations[operations.length - 1].time : session.created_time;
}

export function branchSourceX(parent, child, timelineIndex = buildTimelineIndex([parent, child])) {
  const sourceOperation = sourceOperationForBranch(parent, child);
  if (sourceOperation) return timelineXForTime(eventTimeForOperation(sourceOperation), timelineIndex);
  return timelineXForTime(eventTimeForSessionStart(parent), timelineIndex);
}

export function layoutSessions(sessions) {
  const { childrenByParent, roots } = buildSessionHierarchy(sessions);
  const timelineIndex = buildTimelineIndex(sessions);
  const positions = new Map();
  let laneCursor = 0;

  function placeSession(session, depth) {
    const lane = laneCursor;
    laneCursor += 1;
    positions.set(session.id, {
      startX: timelineXForTime(eventTimeForSessionStart(session), timelineIndex),
      y: lane * NODE_Y_GAP,
      depth,
      lane,
    });

    const children = [...(childrenByParent.get(session.id) || [])].sort((a, b) => {
      const branchDelta = branchSourceX(session, a, timelineIndex) - branchSourceX(session, b, timelineIndex);
      return branchDelta || a.created_time - b.created_time;
    });
    children.forEach((child) => placeSession(child, depth + 1));
  }

  roots.forEach((root, index) => {
    if (index > 0 && laneCursor > 0) laneCursor += ROOT_GAP;
    placeSession(root, 0);
  });

  return positions;
}

export function sessionCurrentX(session, timelineIndex = buildTimelineIndex([session])) {
  if (sessionOperations(session).length === 0) {
    return timelineXForTime(eventTimeForSessionStart(session), timelineIndex);
  }
  return timelineXForTime(latestSessionEventTime(session), timelineIndex) + CURRENT_STATE_GAP;
}

export function internalSessionEdgeIds(session) {
  const operations = sessionOperations(session);
  const edgeIds = [];
  if (operations.length === 0) return edgeIds;

  operations.forEach((op, index) => {
    const opNodeId = operationNodeId(session.id, op.id);
    const previousSource = index === 0 ? sessionStartNodeId(session.id) : operationNodeId(session.id, operations[index - 1].id);
    edgeIds.push(`${previousSource}-${opNodeId}`);
  });

  const finalOperationNodeId = operationNodeId(session.id, operations[operations.length - 1].id);
  edgeIds.push(`${finalOperationNodeId}-${session.id}`);
  return edgeIds;
}

export function activeLineageEdgeIds(sessions, activeSessionId) {
  const { byId } = buildSessionHierarchy(sessions);
  const edgeIds = new Set();
  let current = byId.get(activeSessionId);

  if (current) {
    internalSessionEdgeIds(current).forEach((edgeId) => edgeIds.add(edgeId));
  }

  while (current?.parent_id) {
    const sourceNodeId = sessionEdgeSourceNodeId(current, byId);
    const targetNodeId = sessionEdgeTargetNodeId(current);
    if (sourceNodeId) edgeIds.add(`${sourceNodeId}-${targetNodeId}`);

    const parent = byId.get(current.parent_id);
    const sourceOperation = sourceOperationForBranch(parent, current);
    if (sourceOperation) {
      const parentOperations = sessionOperations(parent);
      const sourceIndex = parentOperations.findIndex((op) => op.id === sourceOperation.id);
      parentOperations.slice(0, sourceIndex + 1).forEach((op, index) => {
        const opNodeId = operationNodeId(parent.id, op.id);
        const previousSource = index === 0 ? sessionStartNodeId(parent.id) : operationNodeId(parent.id, parentOperations[index - 1].id);
        edgeIds.add(`${previousSource}-${opNodeId}`);
      });
    }

    current = parent;
  }

  return edgeIds;
}

function NodeActions({ canDelete, data, beginRename, stopAndRun }) {
  return (
    <span className="session-node-actions">
      <button
        className="node-icon-btn add"
        title="Create child session from this current state"
        aria-label="Create child session from this current state"
        onClick={(event) => stopAndRun(event, () => data.onCreate(data.session.id))}
      >
        <Plus size={13} />
      </button>
      <button
        className="node-icon-btn"
        title="Rename this session"
        aria-label="Rename this session"
        onClick={beginRename}
      >
        <Pencil size={13} />
      </button>
      {canDelete && (
        <button
          className="node-icon-btn danger"
          title="Delete this session branch"
          aria-label="Delete this session branch"
          onClick={(event) => stopAndRun(event, () => data.onDelete(data.session.id))}
        >
          <Trash2 size={13} />
        </button>
      )}
    </span>
  );
}

function SessionNode({ data, selected }) {
  const isActive = data.session.id === data.activeSessionId;
  const canDelete = data.totalSessions > 1 && data.session.parent_id;
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameDraft, setRenameDraft] = useState(data.session.name);
  const [isSavingRename, setIsSavingRename] = useState(false);
  const renameInputRef = useRef(null);

  useEffect(() => {
    if (!isRenaming) setRenameDraft(data.session.name);
  }, [data.session.name, isRenaming]);

  useEffect(() => {
    if (isRenaming) {
      requestAnimationFrame(() => {
        renameInputRef.current?.focus();
        renameInputRef.current?.select();
      });
    }
  }, [isRenaming]);

  function stopOnly(event) {
    event.stopPropagation();
  }

  function stop(event) {
    event.stopPropagation();
    event.preventDefault();
  }

  function stopAndRun(event, fn) {
    stop(event);
    fn?.();
  }

  function beginRename(event) {
    stop(event);
    setRenameDraft(data.session.name);
    setIsRenaming(true);
  }

  async function submitRename(event) {
    event?.stopPropagation();
    event?.preventDefault();
    const cleanName = renameDraft.trim();
    if (!cleanName || isSavingRename) return;

    if (cleanName === data.session.name) {
      setIsRenaming(false);
      return;
    }

    setIsSavingRename(true);
    try {
      const ok = await data.onRename(data.session.id, cleanName);
      if (ok !== false) setIsRenaming(false);
    } finally {
      setIsSavingRename(false);
    }
  }

  function cancelRename(event) {
    event?.stopPropagation();
    event?.preventDefault();
    setRenameDraft(data.session.name);
    setIsRenaming(false);
  }

  return (
    <div
      className={`session-tree-node current-state-node ${isActive ? 'active' : ''} ${selected ? 'selected' : ''}`}
      onClick={() => !isRenaming && data.onActivate(data.session.id)}
      title="Click node to switch to this session"
      data-testid={`session-node-${data.session.id}`}
    >
      <Handle type="target" position={Position.Left} className="tree-handle" />
      <div className="session-node-topline">
        {isRenaming ? (
          <form
            className="session-name-form"
            onSubmit={submitRename}
            onClick={stopOnly}
            onPointerDown={stopOnly}
          >
            <input
              ref={renameInputRef}
              value={renameDraft}
              onChange={(event) => setRenameDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Escape') cancelRename(event);
              }}
              aria-label="Session name"
              disabled={isSavingRename}
            />
            <button
              className="node-icon-btn add"
              title="Save session name"
              aria-label="Save session name"
              type="submit"
              disabled={isSavingRename}
            >
              <Check size={13} />
            </button>
            <button
              className="node-icon-btn"
              title="Cancel rename"
              aria-label="Cancel rename"
              type="button"
              onClick={cancelRename}
              disabled={isSavingRename}
            >
              <X size={13} />
            </button>
          </form>
        ) : (
          <span className="session-node-name" onDoubleClick={beginRename}>{data.session.name}</span>
        )}
        {!isRenaming && (
          <NodeActions canDelete={canDelete} data={data} beginRename={beginRename} stopAndRun={stopAndRun} />
        )}
      </div>
      {data.parentName && (
        <div className="session-node-parent" title={`Parent session: ${data.parentName}`}>
          <GitBranch size={12} />
          <span>From {data.parentName}</span>
        </div>
      )}
      <div className="session-node-meta">
        {data.session.overview.rows.toLocaleString()} rows · {data.session.overview.columns} cols
      </div>
      <div className="session-node-foot">
        {isRenaming ? (isSavingRename ? 'Saving name…' : 'Rename and press Enter') : isActive ? 'Active current state' : 'Click to activate'}
      </div>
      <Handle type="source" position={Position.Right} className="tree-handle" />
    </div>
  );
}

function SessionStartNode({ data }) {
  return (
    <div className="session-start-node" title={`Start snapshot for ${data.session.name}`}>
      <Handle type="target" position={Position.Left} className="tree-handle" />
      <div className="session-start-title">{data.session.name}</div>
      {data.parentName && (
        <div className="session-node-parent compact" title={`Parent session: ${data.parentName}`}>
          <GitBranch size={11} />
          <span>From {data.parentName}</span>
        </div>
      )}
      <div className="session-node-meta">
        {(data.session.created_overview?.rows ?? data.session.overview.rows).toLocaleString()} rows · {data.session.created_overview?.columns ?? data.session.overview.columns} cols
      </div>
      <div className="session-node-foot">Session start</div>
      <Handle type="source" position={Position.Right} className="tree-handle" />
    </div>
  );
}

const nodeTypes = { sessionNode: SessionNode, sessionStartNode: SessionStartNode };

export default function SessionTree({ workspace, onActivate, onCreate, onRename, onDelete }) {
  const provenance = workspace.datasets.find((dataset) => dataset.id === workspace.active_dataset_id)?.provenance;
  const { nodes, edges } = useMemo(() => {
    const { byId, childrenByParent } = buildSessionHierarchy(workspace.sessions);
    const timelineIndex = buildTimelineIndex(workspace.sessions);
    const positions = layoutSessions(workspace.sessions);
    const activeLineage = activeLineageEdgeIds(workspace.sessions, workspace.active_session_id);
    const nodes = [];
    const edges = [];

    workspace.sessions.forEach((session) => {
      const position = positions.get(session.id) || { startX: 0, y: 0 };
      const startX = position.startX;
      const currentX = sessionCurrentX(session, timelineIndex);
      const parent = session.parent_id ? byId.get(session.parent_id) : null;
      const operations = sessionOperations(session);
      const hasOperations = operations.length > 0;
      const collapseCurrentSessionNode = shouldCollapseCurrentSessionNode(session, workspace.active_session_id, childrenByParent);

      if (hasOperations) {
        nodes.push({
          id: sessionStartNodeId(session.id),
          type: 'sessionStartNode',
          position: { x: startX, y: position.y + SESSION_START_Y_OFFSET },
          data: { session, parentName: parent?.name },
          className: 'flow-node session-start-flow-node',
        });
      }

      operations.forEach((op, index) => {
        const opId = operationNodeId(session.id, op.id);
        nodes.push({
          id: opId,
          position: {
            x: timelineXForTime(eventTimeForOperation(op), timelineIndex),
            y: position.y + OPERATION_Y_OFFSET,
          },
          data: { label: op.label },
          className: 'flow-node operation-node'
        });

        const source = index === 0 ? sessionStartNodeId(session.id) : operationNodeId(session.id, operations[index - 1].id);
        const edgeId = `${source}-${opId}`;
        edges.push({
          id: edgeId,
          source,
          target: opId,
          type: OPERATION_EDGE_TYPE,
          className: `flow-edge operation-edge ${activeLineage.has(edgeId) ? 'active-lineage' : ''}`,
        });
      });

      if (hasOperations && !collapseCurrentSessionNode) {
        const source = operationNodeId(session.id, operations[operations.length - 1].id);
        const edgeId = `${source}-${session.id}`;
        edges.push({
          id: edgeId,
          source,
          target: session.id,
          type: OPERATION_EDGE_TYPE,
          className: `flow-edge operation-edge current-state-edge ${activeLineage.has(edgeId) ? 'active-lineage' : ''}`,
        });
      }

      if (!collapseCurrentSessionNode) {
        nodes.push({
        id: session.id,
        type: 'sessionNode',
        position: { x: currentX, y: position.y },
        data: {
          session,
          parentName: hasOperations ? undefined : parent?.name,
          activeSessionId: workspace.active_session_id,
          totalSessions: workspace.sessions.length,
          onActivate,
          onCreate,
          onRename,
          onDelete,
        },
        className: 'flow-node session-node'
        });
      }

      if (session.parent_id) {
        const sourceNodeId = sessionEdgeSourceNodeId(session, byId);
        const targetNodeId = sessionEdgeTargetNodeId(session);
        const edgeId = `${sourceNodeId}-${targetNodeId}`;
        edges.push({
          id: edgeId,
          source: sourceNodeId,
          target: targetNodeId,
          type: BRANCH_EDGE_TYPE,
          animated: workspace.active_session_id === session.id,
          className: `flow-edge session-edge ${activeLineage.has(edgeId) ? 'active-lineage' : ''}`,
        });
      }
    });

    return { nodes, edges };
  }, [workspace, onActivate, onCreate, onRename, onDelete]);

  return (
    <section className="tree-panel" data-testid="session-tree-panel">
      <div className="tree-panel-header">
        <div>
          <p className="section-label">Session tree</p>
        </div>
      </div>
      {provenance?.type === 'merge' && (
        <div className="tree-merge-lineage">
          <span><Database size={13} /><strong>{provenance.left_dataset_name}</strong> · {provenance.left_session_name}</span>
          <span className="tree-merge-kind"><GitMerge size={14} /> {provenance.how === 'outer' ? 'full outer' : provenance.how} merge</span>
          <span><Database size={13} /><strong>{provenance.right_dataset_name}</strong> · {provenance.right_session_name}</span>
        </div>
      )}
      <div id="session-tree-canvas" className="tree-canvas" data-testid="session-tree-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView={false}
            defaultViewport={{ x: 42, y: 44, zoom: 0.92 }}
            minZoom={0.45}
            maxZoom={1.65}
            nodesDraggable
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={22} size={0.8} />
            <Controls showInteractive={false} />
          </ReactFlow>
      </div>
    </section>
  );
}
