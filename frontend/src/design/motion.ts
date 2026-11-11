import type { Transition, Variants } from "framer-motion";

/**
 * 5.1 Global Physics Curves
 */
export const springDynamics: Transition = {
  type: "spring",
  mass: 0.8,
  stiffness: 260,
  damping: 24,
};

export const smoothFadeEasing = [0.25, 0.1, 0.25, 1.0] as const;

export const smoothFadeTransition: Transition = {
  duration: 0.25,
  ease: [0.25, 0.1, 0.25, 1.0],
};

/**
 * 5.2 Component-Specific Motion Behaviors
 */

// A. Page Transitions & Section Reveals
export const pageRevealVariants: Variants = {
  initial: {
    opacity: 0,
    y: 12,
  },
  animate: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.35,
      ease: [0.25, 0.1, 0.25, 1.0],
      staggerChildren: 0.04,
      delayChildren: 0.02,
    },
  },
  exit: {
    opacity: 0,
    y: -8,
    transition: {
      duration: 0.2,
      ease: [0.25, 0.1, 0.25, 1.0],
    },
  },
};

export const sectionRevealChild: Variants = {
  initial: {
    opacity: 0,
    y: 12,
  },
  animate: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.35,
      ease: [0.25, 0.1, 0.25, 1.0],
    },
  },
};

// B. Cards & Container Panels
// Hover: upward 3px (stiffness 400, damping 25)
// Tap: scale 0.99 instantly (100ms)
export const cardInteractiveMotion = {
  whileHover: {
    y: -3,
    transition: {
      type: "spring" as const,
      stiffness: 400,
      damping: 25,
    },
  },
  whileTap: {
    scale: 0.99,
    transition: {
      duration: 0.1,
    },
  },
};

// C. Buttons & Primary Calls-to-Action
// Hover: 1.015x
// Tap: 0.98x
// Physics: stiffness 500, damping 20
export const buttonMotion = {
  whileHover: {
    scale: 1.015,
    transition: {
      type: "spring" as const,
      stiffness: 500,
      damping: 20,
    },
  },
  whileTap: {
    scale: 0.98,
    transition: {
      type: "spring" as const,
      stiffness: 500,
      damping: 20,
    },
  },
};

// D. Dropdown Menus, Context Popovers & Modals
// Initial/Exit: scale 0.96, opacity 0, y: -6
// Animate: scale 1.0, opacity 1, y: 0 over 180ms ease-out
export const modalMotionVariants: Variants = {
  initial: {
    scale: 0.96,
    opacity: 0,
    y: -6,
  },
  animate: {
    scale: 1.0,
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.18,
      ease: "easeOut",
    },
  },
  exit: {
    scale: 0.96,
    opacity: 0,
    y: -6,
    transition: {
      duration: 0.15,
      ease: "easeIn",
    },
  },
};

export const modalBackdropVariants: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.2 } },
  exit: { opacity: 0, transition: { duration: 0.18 } },
};

// Toast & Floating Alert Slide-in Trajectory (from top right quadrant)
export const toastSlideVariants: Variants = {
  initial: {
    x: 80,
    opacity: 0,
    scale: 0.96,
  },
  animate: {
    x: 0,
    opacity: 1,
    scale: 1,
    transition: {
      type: "spring",
      mass: 0.8,
      stiffness: 320,
      damping: 25,
    },
  },
  exit: {
    x: 60,
    opacity: 0,
    scale: 0.95,
    transition: {
      duration: 0.2,
      ease: [0.25, 0.1, 0.25, 1.0],
    },
  },
};
