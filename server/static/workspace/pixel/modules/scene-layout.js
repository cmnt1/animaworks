const TEMPLATE_URL = new URL("../assets/scene.json", import.meta.url);
const HUMAN_ID = "human";
export const LOGICAL_CANVAS_WIDTH = 1120;
export const LOGICAL_CANVAS_HEIGHT = 736;

export function resolveBasePath() {
  const configured = document.querySelector('meta[name="aw-base-path"]')?.content || "";
  if (configured && !configured.includes("__AW_BASE__")) return configured.replace(/\/$/, "");
  const marker = "/workspace/pixel";
  const index = location.pathname.indexOf(marker);
  return index > 0 ? location.pathname.slice(0, index) : "";
}

function normalizedAnimas(animas) {
  return (Array.isArray(animas) ? animas : [])
    .filter((entry) => entry?.name && !entry.is_human && entry.name.toLowerCase() !== "librarian")
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
  const columns = Math.max(
    1,
    Math.min(count || 1, options.columns || 4, Math.floor((x2 - x1 + 1) / stepX)),
  );
  const rows = Math.max(1, Math.ceil(count / columns));
  const dense = rows > 2;
  const top = y1 + (dense ? 2 : (options.topOffset ?? 3));
  const rowStep = options.rowStep || 4;
  const bottom = Math.max(top, y2 - (dense ? 5 : 7));
  const candidates = [];
  const columnLeft = x1 + (dense ? 1 : 2);
  const columnRight = Math.max(columnLeft, x2 - 2);
  const columnStart = (columnLeft + columnRight - (columns - 1) * stepX) / 2;
  for (let row = 0; row < rows; row += 1) {
    const y = Math.min(bottom, top + row * rowStep);
    const rowCount = Math.min(columns, count - row * columns);
    const rowStart = columnStart + (columns - rowCount) * stepX / 2;
    for (let column = 0; column < rowCount; column += 1) {
      const x = rowCount === 1
        ? Math.round((columnLeft + columnRight) / 2)
        : Math.round(rowStart + column * stepX);
      if (!options.avoidRect || !overlapsRect(x, y, options.avoidRect)) candidates.push([x, y]);
    }
  }
  for (let y = top; candidates.length < count && y <= y2 - 3; y += 3) {
    for (let x = columnLeft; candidates.length < count && x <= columnRight; x += stepX) {
      if ((!options.avoidRect || !overlapsRect(x, y, options.avoidRect)) &&
          !candidates.some(([candidateX, candidateY]) => candidateX === x && candidateY === y)) {
        candidates.push([x, y]);
      }
    }
  }
  return candidates.slice(0, count);
}

function companyRects(groups, rule) {
  const top = rule.top ?? 4;
  const bottom = rule.bottom ?? 22;
  const left = rule.left ?? 1;
  const right = rule.right ?? 39;
  const fit = (group, slotLeft, slotRight) => {
    const slotWidth = slotRight - slotLeft + 1;
    const columns = Math.max(3, Math.min(5, rule.desk_columns || 4));
    const rows = Math.max(1, Math.ceil(group.members.length / columns));
    const width = Math.min(slotWidth, Math.max(10, columns * 4 + 3));
    const height = Math.min(
      bottom - top + 1,
      rule.height || Math.max(15, 11 + (rows - 1) * (rule.desk_row_step || 4)),
    );
    const x1 = Math.round((slotLeft + slotRight + 1 - width) / 2);
    return [x1, top, x1 + width - 1, top + height - 1];
  };
  if (groups.length <= 1) return [fit(groups[0], left + 2, right - 2)];
  if (groups.length === 2) {
    if (rule.centerRect) {
      return [
        fit(groups[0], left, rule.centerRect[0] - 2),
        fit(groups[1], rule.centerRect[2] + 2, right - 1),
      ];
    }
    const middle = Math.floor((left + right) / 2);
    return [
      fit(groups[0], left + 1, middle - 5),
      fit(groups[1], middle + 4, right - 2),
    ];
  }
  const totalWidth = right - left + 1;
  return groups.map((group, index) => {
    const slotLeft = left + Math.floor((totalWidth * index) / groups.length);
    const slotRight = left + Math.floor((totalWidth * (index + 1)) / groups.length) - 1;
    return fit(group, slotLeft, slotRight);
  });
}

function addCompanyProps(props, plants, group, rect) {
  const [x1, y1, x2, y2] = rect;
  const width = x2 - x1 + 1;
  if (width >= 10) {
    props[`lounge_${group.index + 1}`] = {
      tile: [x1 + 1, y2 - 3],
      w: 3,
      h: 2,
      sprite: "sofa",
    };
    props[`lounge_rug_${group.index + 1}`] = {
      tile: [x1 + 1, y2 - 4],
      w: 4.5,
      h: 3,
      sprite: "rug",
      under: true,
    };
    props[`side_table_${group.index + 1}`] = {
      tile: [x1 + 4, y2 - 2],
      w: 1.75,
      h: 1.375,
      sprite: "side_table",
      kind: "meeting",
      company: group.company,
    };
    props[`bookshelf_${group.index + 1}`] = {
      tile: [Math.max(x1 + 1, x2 - 3), y2 - 3],
      w: 3.5,
      h: 2,
      sprite: "bookshelf",
    };
    props[`trash_${group.index + 1}`] = {
      tile: [x2 - 1, y2 - 1],
      w: 0.625,
      h: 0.875,
      sprite: "trash_bin",
    };
  }
  props[`poster_${group.index + 1}`] = {
    tile: [Math.min(x2 - 1, x1 + Math.floor(width / 2)), 2],
    w: 0.75,
    h: 1.125,
    sprite: group.index % 2 ? "poster_b" : "poster_a",
    wall: true,
  };
  props[`poster_extra_${group.index + 1}`] = {
    tile: [group.index % 2 ? x1 + 2 : x2 - 3, 2],
    w: 0.75,
    h: 1.125,
    sprite: group.index % 2 ? "poster_b" : "poster_a",
    wall: true,
  };
  props[`wall_clock_${group.index + 1}`] = {
    tile: [group.index % 2 ? x2 - 1 : x1 + 1, 3],
    w: 1,
    h: 1,
    decor: "wall_clock",
    wall: true,
  };
  props[`wall_shelf_${group.index + 1}`] = {
    tile: [group.index % 2 ? x1 : x2 - 2, 3],
    w: 2,
    h: 1,
    decor: "wall_shelf",
    wall: true,
  };
  props[`stand_lamp_${group.index + 1}`] = {
    tile: [group.index % 2 ? x2 : x1, y1 + 5],
    w: 1,
    h: 2,
    decor: "stand_lamp",
  };
  plants.push(
    [x1, y1 + 1],
    [x2 - 1, y1 + 1],
    [x1, y2 - 1],
    [x2 - 1, y2 - 4],
  );
}

export function sampleAnimas(count = 12) {
  const parsed = Number.parseInt(count, 10);
  const size = Math.max(1, Math.min(60, Number.isFinite(parsed) ? parsed : 12));
  return Array.from({ length: size }, (_, index) => ({
    name: `anima-${index + 1}`,
    company: index < Math.ceil(size / 2) ? "alpha" : "beta",
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
  const plazaRule = layout.plaza || {};
  const entranceRule = layout.entrance || {};
  const humanRect = humanRule.zone || [17, 8, 21, 14];
  const tile = template.canvas?.tile || 32;
  const canvasWidth = LOGICAL_CANVAS_WIDTH;
  const canvasHeight = LOGICAL_CANVAS_HEIGHT;
  const deskColumns = Math.max(
    3,
    Math.min(5, groups.length >= 3 ? 3 : companyRule.desk_columns || 4),
  );
  const rowStep = companyRule.desk_row_step || 3;
  const companyHeight = companyRule.height || 15;
  const growth = 0;
  const canvasColumns = Math.floor(canvasWidth / tile);
  const roomBottom = Math.floor(canvasHeight / tile) - 3;
  const rects = companyRects(groups, {
    ...companyRule,
    bottom: Math.min((companyRule.bottom ?? roomBottom) + growth, roomBottom),
    centerRect: humanRect,
    desk_columns: deskColumns,
    height: companyHeight,
  });
  const plazaTop = Math.min(roomBottom, (plazaRule.top ?? roomBottom) + growth);
  const plazaBottom = Math.min(roomBottom, (plazaRule.bottom ?? roomBottom) + growth);
  const zones = {};
  const desks = {};
  const pathTemplate = pathRule.zone || [18, 14, 21, 22];
  const pathZone = [pathTemplate[0], pathTemplate[1], pathTemplate[2], roomBottom];
  const entranceTemplate = entranceRule.zone || [16, 21, 23, 25];
  const entranceWidth = entranceTemplate[2] - entranceTemplate[0] + 1;
  const entranceAxisX = (pathZone[0] + pathZone[2] + 1) / 2;
  const entranceLeft = Math.round(entranceAxisX - entranceWidth / 2);
  const entranceZone = [
    entranceLeft,
    entranceTemplate[1] + growth,
    entranceLeft + entranceWidth - 1,
    roomBottom,
  ];
  const doorTile = [
    entranceAxisX - 3,
    (entranceRule.door || [18, 23])[1] + growth,
  ];
  const props = {
    whiteboard: { tile: [canvasColumns / 2 - 2.5, 1], w: 5, h: 2.25, sprite: "whiteboard" },
    bookshelf: { tile: [8, 1], w: 3.5, h: 2, sprite: "bookshelf" },
    refreshment: { tile: [canvasColumns - 4, 1], w: 3, h: 2.25, sprite: "coffee_corner" },
    welcome_mat: {
      tile: [doorTile[0] + 1.5, doorTile[1] + 1.75],
      w: 3,
      h: 1.5,
      sprite: "welcome_mat",
    },
    entrance: {
      tile: doorTile,
      w: 6,
      h: 4,
      sprite: "entrance",
      architectural: true,
      bottom_inset: 128,
      service_tile: [Math.round(doorTile[0] + 4.5), doorTile[1] - 2],
    },
    trolley: {
      tile: [pathZone[0] - 3, Math.min(roomBottom - 1, plazaTop + 1)],
      w: 1.75,
      h: 1.75,
      sprite: "trolley",
    },
    path_trash: {
      tile: [pathZone[2] + 2, Math.min(roomBottom, plazaTop + 2)],
      w: 0.625,
      h: 0.875,
      sprite: "trash_bin",
    },
    corridor_lamp_left: {
      tile: [pathZone[0] - 0.5, pathZone[1]],
      w: 1,
      h: 1,
      decor: "guide_lamp",
    },
    corridor_sign_left: {
      tile: [pathZone[0] - 0.5, pathZone[1] + 1],
      w: 1,
      h: 1,
      sprite: "sign_stand",
      text: "←",
    },
    corridor_plant_left: {
      tile: [pathZone[0] - 0.5, pathZone[1] + 2],
      w: 1,
      h: 1,
      sprite: "plant_large",
    },
    corridor_plant_right: {
      tile: [pathZone[2] + 0.5, pathZone[1]],
      w: 1,
      h: 1,
      sprite: "plant_large",
    },
    corridor_sign_right: {
      tile: [pathZone[2] + 0.5, pathZone[1] + 1],
      w: 1,
      h: 1,
      sprite: "sign_stand",
      text: "→",
      flip: true,
    },
    corridor_lamp_right: {
      tile: [pathZone[2] + 0.5, pathZone[1] + 2],
      w: 1,
      h: 1,
      decor: "guide_lamp",
    },
    cat: { tile: [rects.at(-1)[0] + 2, rects.at(-1)[3] - 4], w: 0.875, h: 0.625, sprite: "cat" },
    cat_bed: { tile: [rects.at(-1)[0] + 3, rects.at(-1)[3] - 3], w: 1, h: 0.625, sprite: "cat_bed" },
  };
  const plants = [];

  groups.forEach((group, index) => {
    const rect = rects[index];
    zones[group.key] = {
      label: group.company,
      rect,
      floor: index % 2 ? "wood_cool" : "wood_warm",
      kind: "company",
      company: group.company,
    };
    const groupColumns = group.members.length > 9 ? 4 : deskColumns;
    const positions = gridForZone(rect, group.members.length, {
      columns: groupColumns,
      stepX: groupColumns === 4 ? 3 : (companyRule.desk_column_step || 4),
      rowStep,
      topOffset: companyRule.desk_top_offset ?? 3,
      avoidRect: humanRect,
    });
    group.members.forEach((anima, memberIndex) => {
      const position = positions[memberIndex] || [rect[0] + 2, rect[1] + 3];
      const inward = groups.length === 2 ? (index === 0 ? 2 : -2) : 0;
      desks[anima.id] = {
        tile: [position[0] + inward, position[1]],
        facing: "down",
        company: group.company,
        sample_index: anima.index,
      };
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
    rect: pathZone,
    floor: pathRule.floor || "stone_warm",
    kind: "path",
  };
  zones.entrance = {
    label: "ENTRANCE",
    rect: entranceZone,
    floor: null,
    kind: "entrance",
  };
  zones.plaza = {
    label: "",
    rect: [
      plazaRule.left ?? 1,
      plazaTop,
      plazaRule.right ?? canvasColumns - 2,
      plazaBottom,
    ],
    floor: "plaza",
    kind: "plaza",
  };
  for (const x of [2, 7, 11, canvasColumns - 9, canvasColumns - 3]) {
    plants.push([x, plazaTop]);
  }
  desks[HUMAN_ID] = {
    tile: humanRule.desk || [19, 11],
    facing: "down",
    wide: 2,
    company: HUMAN_ID,
    is_human: true,
  };

  return {
    canvas: {
      w: canvasWidth,
      h: canvasHeight,
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
    canvas: {
      ...scene.canvas,
      w: LOGICAL_CANVAS_WIDTH,
      h: LOGICAL_CANVAS_HEIGHT,
    },
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
