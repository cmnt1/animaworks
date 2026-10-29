import { getState, setState } from "../state.js";
import {
  initOffice,
  disposeOffice as disposeThreeOffice,
  getScene,
  getDesks,
  setCharacterUpdateHook,
  setCharacterClickHandler,
  registerClickTarget,
  highlightDesk,
  clearHighlight,
  getFloorDimensions,
  getObstacles,
} from "../office3d.js";
import {
  initCharacters,
  createCharacter,
  updateAllCharacters,
  getCharacterGroup,
  getCharacterHome,
  setAppearance,
  updateCharacterState,
} from "../character.js";
import { setLive2dAppearance } from "../live2d.js";
import { createNavGrid } from "../navigation.js";
import {
  initMovement,
  registerCharacter,
  updateMovements,
  moveTo,
  moveToHome,
  stopMovement,
  isMoving,
} from "../movement.js";
import { computePOIs, initIdleBehaviors, updateIdleBehaviors } from "../idle_behavior.js";
import {
  initInteractions,
  showMessageEffect,
  showConversation,
  updateInteractions,
  dispose as disposeInteractions,
} from "../interactions.js";
import { selectAnima } from "../anima.js";
import { mapAnimaStatusToAnim } from "../anima-status.js";
import { createLogger } from "../../../shared/logger.js";

const logger = createLogger("ws-office-3d-renderer");

function cleanupOffice3d() {
  setCharacterClickHandler(null);
  setCharacterUpdateHook(null);
  disposeInteractions();
  disposeThreeOffice();
  setState({ officeInitialized: false });
}

/** Initialize the existing Three.js office and return its renderer handle. */
export async function mountOffice3d(dom) {
  setState({ officeInitialized: false });

  try {
    const { animas } = getState();
    initOffice(dom.officeCanvas, animas);

    const scene = getScene();
    if (!scene) throw new Error("3D office scene was not created");
    initCharacters(scene);

    setCharacterUpdateHook((dt, elapsed) => {
      updateAllCharacters(dt, elapsed);
      updateMovements(dt);
      updateIdleBehaviors(dt);
      updateInteractions(dt);
    });

    const desks = getDesks();
    for (const anima of animas) {
      if (anima.appearance) {
        setAppearance(anima.name, anima.appearance);
        setLive2dAppearance(anima.name, anima.appearance);
      }
      const deskPos = desks[anima.name];
      if (deskPos) {
        const group = await createCharacter(anima.name, {
          x: deskPos.x,
          y: 0,
          z: deskPos.z - 0.55,
        });
        if (group) {
          group.traverse((child) => {
            if (child.isMesh) registerClickTarget(anima.name, child);
          });
        }
        updateCharacterState(anima.name, mapAnimaStatusToAnim(anima.status));
      }
    }

    const { width: floorWidth, depth: floorDepth } = getFloorDimensions();
    const navGrid = createNavGrid(floorWidth, floorDepth, getObstacles());
    initMovement(navGrid, floorWidth, floorDepth);

    for (const anima of animas) {
      const group = getCharacterGroup(anima.name);
      const home = getCharacterHome(anima.name);
      if (group && home) registerCharacter(anima.name, group, home);
    }

    const movementSystem = { moveTo, moveToHome, stopMovement, isMoving };
    const characterMap = Object.fromEntries(animas.map((anima) => [anima.name, true]));
    initInteractions(scene, characterMap, movementSystem);
    initIdleBehaviors(characterMap, movementSystem, computePOIs(floorWidth, floorDepth));

    setCharacterClickHandler((animaName) => selectAnima(animaName));
    const { selectedAnima } = getState();
    if (selectedAnima) highlightDesk(selectedAnima);

    setState({ officeInitialized: true });
    let disposed = false;
    return {
      highlight(name) {
        if (name == null) clearHighlight();
        else highlightDesk(name);
      },
      dispose() {
        if (disposed) return;
        disposed = true;
        cleanupOffice3d();
      },
    };
  } catch (err) {
    logger.error("Failed to initialize 3D office", { error: err.message });
    cleanupOffice3d();
    return null;
  }
}
