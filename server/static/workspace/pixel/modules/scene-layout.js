const TEMPLATE_URL = new URL("../assets/scene.json", import.meta.url);
const HUMAN_ID = "human";

export function resolveBasePath() {
  const configured = document.querySelector('meta[name="aw-base-path"]')?.content || "";
  if (configured && !configured.includes("__AW_BASE__")) return configured.replace(/\/$/, "");
  const marker = "/workspace/pixel";
  const index = location.pathname.indexOf(marker);
  return index > 0 ? location.pathname.slice(0, index) : "";
}

function normalizedAnimas(animas) {
  return (Array.isArray(animas) ? animas : [])
    .filter((entry) => entry?.name && !entry.is_human)
    .map((entry, index) => ({
      ...entry,
      id: String(entry.name).trim().toLowerCase(),
      company: String(entry.company || "default").trim() || "default",
      index,
    }));
}

function companyGroups(animas) {
  const groups = new Map();
  for (const anima of animas) {
    if (!groups.has(anima.company)) groups.set(anima.company, []);
    groups.get(anima.company).push(anima);
  }
  return [...groups.entries()].map(([company, members], index) => ({
    company,
    members,
    key: `company_${index + 1}`,
    index,
  }));
}

function overlapsRect(x, y, rect) {
  return x >= rect[0] - 1 && x <= rect[2] + 1 && y >= rect[1] - 1 && y <= rect[3] + 1;
}

function gridForZone(rect, count, options = {}) {
  const [x1, y1, x2, y2] = rect;
  const stepX = options.stepX || 4;
  const columns = Math.max(1, Math.min(options.columns || 4, Math.floor((x2 - x1 + 1) / stepX)));
  const candidates = [];
  for (let row = 0; row < Math.max(1, Math.ceil(count / columns) + 2); row += 1) {
    const y = Math.min(y2 - 2, y1 + 3 + row * (options.stepY || 6));
    for (let column = 0; column < columns; column += 1) {
      const x = Math.min(x2 - 1, x1 + 3 + column * stepX);
      if (!options.avoidRect || !overlapsRect(x, y, options.avoidRect)) candidates.push([x, y]);
    }
  }
  return candidates.slice(0, count);
}

function companyRects(groups, rule) {
  const top = rule.top ?? 4;
  const bottom = rule.bottom ?? 22;
  const left = rule.left ?? 1;
  const right = rule.right ?? 39;
  if (groups.length <= 1) return [[left, top, right, bottom]];
  if (groups.length === 2) {
    const middle = Math.floor((left + right) / 2);
    return [[left, top, middle - 2, bottom], [middle + 2, top, right, bottom]];
  }
  const totalWidth = right - left + 1;
  return groups.map((_, index) => {
    const x1 = left + Math.floor((totalWidth * index) / groups.length);
    const x2 = left + Math.floor((totalWidth * (index + 1)) / groups.length) - 1;
    return [x1, top, x2, bottom];
  });
}

function addCompanyProps(props, plants, group, rect) {
  const [x1, y1, x2, y2] = rect;
  const width = x2 - x1 + 1;
  const meetingX = Math.max(x1 + 1, x2 - 4);
  const meetingY = Math.max(y1 + 7, y2 - 4);
  props[`meeting_${group.index + 1}`] = {
    tile: [meetingX, meetingY],
    w: 3,
    h: 2,
    sprite: "meeting_table",
    kind: "meeting",
    company: group.company,
  };
  props[`meeting_rug_${group.index + 1}`] = {
    tile: [Math.max(x1, meetingX - 1), Math.max(y1, meetingY - 1)],
    w: 5,
    h: 4,
    sprite: "rug",
    under: true,
  };
  if (width >= 14) {
    props[`lounge_${group.index + 1}`] = {
      tile: [x1 + 1, y2 - 3],
      w: 3,
      h: 2,
      sprite: "sofa",
    };
    props[`lounge_rug_${group.index + 1}`] = {
      tile: [x1, y2 - 4],
      w: 5,
      h: 4,
      sprite: "rug",
      under: true,
    };
    props[`side_table_${group.index + 1}`] = {
      tile: [x1 + 4, y2 - 2],
      w: 2,
      h: 2,
      sprite: "side_table",
    };
  }
  props[`poster_${group.index + 1}`] = {
    tile: [Math.min(x2 - 1, x1 + Math.floor(width / 2)), 2],
    w: 1,
    h: 2,
    sprite: group.index % 2 ? "poster_b" : "poster_a",
  };
  plants.push([x1, y1], [x2 - 1, y1], [x1, y2 - 1], [x2 - 1, y2 - 1]);
}

export function sampleAnimas() {
  return Array.from({ length: 6 }, (_, index) => ({
    name: `anima-${index + 1}`,
    company: index < 3 ? "alpha" : "beta",
    status: "idle",
  }));
}

export function generateScene(animas, template) {
  const members = normalizedAnimas(animas);
  const groups = companyGroups(members);
  if (!groups.length) return generateScene(sampleAnimas(), template);
  const layout = template.layout || {};
  const companyRule = layout.company_area || {};
  const humanRule = layout.human_gate || {};
  const pathRule = layout.path || {};
  const entranceRule = layout.entrance || {};
  const humanRect = humanRule.zone || [17, 8, 21, 14];
  const rects = companyRects(groups, companyRule);
  const tile = template.canvas?.tile || 32;
  const zones = {};
  const desks = {};
  const entranceZone = entranceRule.zone || [16, 22, 23, 25];
  const doorTile = entranceRule.door || [19, 24];
  const props = {
    whiteboard: { tile: [17, 1], w: 6, h: 2, sprite: "whiteboard" },
    bookshelf: { tile: [10, 1], w: 4, h: 2, sprite: "bookshelf" },
    refreshment: { tile: [35, 1], w: 3, h: 2, sprite: "coffee" },
    welcome_mat: {
      tile: [entranceZone[0] + 2, entranceZone[1] + 1],
      w: 4,
      h: 2,
      sprite: "welcome_mat",
      under: true,
    },
    door: { tile: doorTile, w: 2, h: 2, sprite: "door" },
    parcel_door: { tile: [doorTile[0] + 2, doorTile[1] - 1], w: 1, h: 1, sprite: "parcel_stack" },
    trolley: { tile: [19, 18], w: 2, h: 2, sprite: "trolley" },
    sign_stand: { tile: [17, 22], w: 1, h: 2, sprite: "sign_stand" },
    cat: { tile: [25, 14], w: 1, h: 1, sprite: "cat" },
    cat_bed: { tile: [26, 15], w: 1, h: 1, sprite: "cat_bed" },
  };
  const plants = [];
  let deskIndex = 0;

  groups.forEach((group, index) => {
    const rect = rects[index];
    zones[group.key] = {
      label: group.company,
      rect,
      floor: index % 2 ? "wood_cool" : "wood_warm",
      kind: "company",
      company: group.company,
    };
    const positions = gridForZone(rect, group.members.length, {
      columns: groups.length >= 3 ? 3 : companyRule.desk_columns || 4,
      stepX: companyRule.desk_column_step || 4,
      stepY: companyRule.desk_row_step || 6,
      avoidRect: humanRect,
    });
    group.members.forEach((anima, memberIndex) => {
      const itemNumber = String((deskIndex % 14) + 1).padStart(2, "0");
      desks[anima.id] = {
        tile: positions[memberIndex] || [rect[0] + 2, rect[1] + 3],
        facing: "down",
        company: group.company,
        item: `item_${itemNumber}`,
        sample_index: anima.index,
      };
      deskIndex += 1;
    });
    addCompanyProps(props, plants, group, rect);
  });

  zones.human = {
    label: humanRule.label || "HUMAN",
    rect: humanRect,
    floor: "carpet_blue",
    kind: "human",
  };
  zones.path = {
    label: "",
    rect: pathRule.zone || [18, 14, 21, 22],
    floor: "carpet_blue",
    kind: "path",
  };
  zones.entrance = {
    label: "ENTRANCE",
    rect: entranceZone,
    floor: "mat",
    kind: "entrance",
  };
  desks[HUMAN_ID] = {
    tile: humanRule.desk || [19, 11],
    facing: "down",
    wide: 2,
    company: HUMAN_ID,
    is_human: true,
    item: "item_14",
  };

  return {
    canvas: {
      w: template.canvas?.w || 1280,
      h: template.canvas?.h || 832,
      tile,
    },
    human_id: HUMAN_ID,
    zones,
    desks,
    props: { ...props, plants },
    walk: { cross_company_via: pathRule.cross_company_via || [19, 13] },
    lighting: template.lighting || {
      day: { tint: "#fff6e8", window: "city_day" },
      night: { tint: "#2a2a4a", window: "city_night" },
    },
  };
}

function normalizeRuntimeScene(scene) {
  const humanId = String(scene.human_id || HUMAN_ID).toLowerCase();
  return {
    ...scene,
    human_id: humanId,
    desks: Object.fromEntries(
      Object.entries(scene.desks || {}).map(([id, desk]) => [String(id).toLowerCase(), desk]),
    ),
  };
}

export async function loadScene(animas) {
  const templateResponse = await fetch(TEMPLATE_URL, { cache: "no-store" });
  if (!templateResponse.ok) throw new Error(`scene template: HTTP ${templateResponse.status}`);
  const template = await templateResponse.json();
  let response;
  try {
    response = await fetch(`${resolveBasePath()}/api/workspace/pixel/scene`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
  } catch (error) {
    if (!(error instanceof TypeError)) throw error;
    return generateScene(animas, template);
  }
  if (response.ok) return normalizeRuntimeScene(await response.json());
  if (response.status !== 404) throw new Error(`runtime scene: HTTP ${response.status}`);
  return generateScene(animas, template);
}
