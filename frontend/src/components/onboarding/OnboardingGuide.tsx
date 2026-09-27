"use client";

import { ArrowRight, BarChart3, BriefcaseBusiness, Check, CheckCircle2, CircleHelp, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { cn } from "@/lib/cn";
import { createClient } from "@/lib/supabase/client";

const STORAGE_KEY = "pp:onboarding:v1";

const STEPS = [
  {
    title: "Create your portfolio",
    body: "Set your capital and risk preference. PortfolioPilot uses these as guardrails.",
    Icon: BriefcaseBusiness,
  },
  {
    title: "Review a proposed plan",
    body: "See what the model would include, leave out, and why—before anything changes.",
    Icon: Search,
  },
  {
    title: "Place orders yourself",
    body: "Use the clear checklist at your own broker. PortfolioPilot never places orders.",
    Icon: CheckCircle2,
  },
  {
    title: "Keep track",
    body: "Record completed orders and see your portfolio progress in one place.",
    Icon: BarChart3,
  },
];

function readLocalFlag(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "done";
  } catch {
    return false;
  }
}

function writeLocalFlag() {
  try {
    window.localStorage.setItem(STORAGE_KEY, "done");
  } catch {
    // Storage can be unavailable; the Supabase flag still prevents repeats.
  }
}

type Props = {
  // Show automatically for users who haven't completed onboarding.
  autoOpen: boolean;
};

// Renders the nav's "?" help button together with the guide dialog it opens.
export function OnboardingGuide({ autoOpen }: Props) {
  const [open, setOpen] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  // Only the automatic first-time showing needs to persist completion.
  const persistOnClose = useRef(false);

  useEffect(() => {
    if (!autoOpen || readLocalFlag()) return;
    let cancelled = false;
    void createClient()
      .auth.getUser()
      .then(({ data: { user } }) => {
        if (cancelled || !user) return;
        if (user.user_metadata?.onboarding_completed === true) {
          writeLocalFlag();
          return;
        }
        persistOnClose.current = true;
        setStepIndex(0);
        setOpen(true);
      });
    return () => {
      cancelled = true;
    };
  }, [autoOpen]);

  function handleClose() {
    setOpen(false);
    if (!persistOnClose.current) return;
    persistOnClose.current = false;
    writeLocalFlag();
    void createClient()
      .auth.updateUser({ data: { onboarding_completed: true } })
      .then(({ error }) => {
        if (error) console.error("Failed to save onboarding status:", error);
      });
  }

  const step = STEPS[stepIndex];
  const isLast = stepIndex === STEPS.length - 1;

  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        onClick={() => {
          setStepIndex(0);
          setOpen(true);
        }}
        aria-label="Open getting started guide"
        title="Getting started"
      >
        <CircleHelp size={18} aria-hidden="true" />
      </Button>
      <Modal open={open} onClose={handleClose} labelledBy="onboarding-title" describedBy="onboarding-body" wide>
        <div className="p-6">
          <div className="mb-7 flex items-start justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-primary">
                Getting started · {stepIndex + 1} of {STEPS.length}
              </p>
              <h2 id="onboarding-title" className="mt-2 text-xl font-bold">
                {step.title}
              </h2>
            </div>
            <Button variant="ghost" size="icon" aria-label="Close guide" onClick={handleClose}>
              <X size={18} aria-hidden="true" />
            </Button>
          </div>
          <div className="mb-8 rounded-md bg-muted p-5">
            <div className="mb-4 grid size-11 place-items-center rounded-md bg-primary text-primary-foreground">
              <step.Icon aria-hidden="true" />
            </div>
            <p id="onboarding-body" className="leading-7 text-muted-foreground">
              {step.body}
            </p>
          </div>
          <div className="flex items-center justify-between gap-3">
            <div className="flex gap-1.5" aria-hidden="true">
              {STEPS.map((item, index) => (
                <span
                  key={item.title}
                  className={cn("h-1.5 rounded-full transition-all", index === stepIndex ? "w-7 bg-primary" : "w-2 bg-border")}
                />
              ))}
            </div>
            <div className="flex gap-2">
              {stepIndex > 0 && (
                <Button variant="outline" onClick={() => setStepIndex(stepIndex - 1)}>
                  Back
                </Button>
              )}
              {isLast ? (
                <Button onClick={handleClose} autoFocus>
                  Finish <Check size={16} aria-hidden="true" />
                </Button>
              ) : (
                <Button onClick={() => setStepIndex(stepIndex + 1)} autoFocus>
                  Next <ArrowRight size={16} aria-hidden="true" />
                </Button>
              )}
            </div>
          </div>
        </div>
      </Modal>
    </>
  );
}
