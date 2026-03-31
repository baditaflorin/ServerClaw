import { z } from "zod";

const operatorIdPattern = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const usernamePattern = /^[A-Za-z0-9._-]+$/;
const sshKeyPrefixPattern = /^(ssh-|ecdsa-sha2-|sk-ssh-|sk-ecdsa-)/;

const requiredNameSchema = z.string().trim().min(1, "Name is required.");
const requiredEmailSchema = z.string().trim().min(1, "Email is required.").email("Enter a valid email address.");
const optionalEmailSchema = z
  .string()
  .trim()
  .refine((value) => value === "" || z.email().safeParse(value).success, "Enter a valid email address.");
const optionalOperatorIdSchema = z
  .string()
  .trim()
  .refine((value) => value === "" || operatorIdPattern.test(value), "Use lowercase letters, numbers, and hyphens only.");
const optionalUsernameSchema = z
  .string()
  .trim()
  .refine((value) => value === "" || usernamePattern.test(value), "Use letters, numbers, dots, underscores, or hyphens only.");
const optionalDeviceNameSchema = z.string().trim().max(63, "Keep the device name under 64 characters.");
const optionalReasonSchema = z.string().trim().max(500, "Keep the audit note under 500 characters.");
const sshKeySchema = z
  .string()
  .trim()
  .refine((value) => value === "" || sshKeyPrefixPattern.test(value), "Paste a full SSH public key.");

export const operatorRoleSchema = z.enum(["admin", "operator", "viewer"]);

export const onboardFormSchema = z
  .object({
    name: requiredNameSchema,
    email: requiredEmailSchema,
    role: operatorRoleSchema,
    ssh_key: sshKeySchema,
    operator_id: optionalOperatorIdSchema,
    keycloak_username: optionalUsernameSchema,
    tailscale_login_email: optionalEmailSchema,
    tailscale_device_name: optionalDeviceNameSchema,
    dry_run: z.boolean(),
  })
  .superRefine((value, context) => {
    if (value.role !== "viewer" && value.ssh_key.length === 0) {
      context.addIssue({
        code: "custom",
        message: "SSH public key is required for admin and operator roles.",
        path: ["ssh_key"],
      });
    }
  });

export const offboardFormSchema = z.object({
  operator_id: z.string().min(1, "Select an operator."),
  reason: optionalReasonSchema,
  dry_run: z.boolean(),
});

export const syncFormSchema = z.object({
  operator_id: optionalOperatorIdSchema,
  dry_run: z.boolean(),
});

export type OnboardFormValues = z.infer<typeof onboardFormSchema>;
export type OffboardFormValues = z.infer<typeof offboardFormSchema>;
export type SyncFormValues = z.infer<typeof syncFormSchema>;

export const onboardFormDefaults: OnboardFormValues = {
  name: "",
  email: "",
  role: "operator",
  ssh_key: "",
  operator_id: "",
  keycloak_username: "",
  tailscale_login_email: "",
  tailscale_device_name: "",
  dry_run: false,
};

export const offboardFormDefaults: OffboardFormValues = {
  operator_id: "",
  reason: "",
  dry_run: false,
};

export const syncFormDefaults: SyncFormValues = {
  operator_id: "",
  dry_run: false,
};
