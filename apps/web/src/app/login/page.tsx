import { redirect } from "next/navigation";
import { login } from "@/app/actions/auth";
import { AuthForm } from "@/components/AuthForm";
import { currentUser } from "@/lib/auth";

export default async function LoginPage() {
  if (await currentUser()) redirect("/desk");
  return <AuthForm action={login} mode="login" />;
}
