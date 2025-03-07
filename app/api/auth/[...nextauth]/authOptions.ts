import CredentialsProvider from "next-auth/providers/credentials";
import { AuthOptions } from "next-auth";
import { authLogin, authLoginFacebook, authLogout } from "../../services/auth";
import { DefaultSession } from "next-auth";
import FacebookProvider from "next-auth/providers/facebook"; // Импорт FacebookProvider

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      access?: string;
      refresh?: string;
    } & DefaultSession["user"];
  }

  interface User {
    access?: string;
    refresh?: string;
  }

  interface JWT {
    access?: string;
    refresh?: string;
    id?: string;
    email?: string;
  }
}

export const authOptions: AuthOptions = {
  session: {
    strategy: "jwt",
  },
  events: {
    async signOut({ token }) {
      console.log("=== signOut event ===");
      console.log("token при signOut:", token);

      if (token?.refresh && token?.access) {
        try {
          console.log("Вызываем authLogout...");
          await authLogout(token.refresh as string, token.access as string);
        } catch (error) {
          console.error("Error during logout:", error);
        }
      }
    },
  },
  providers: [
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        email: { label: "Email", type: "text" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        console.log("=== CredentialsProvider.authorize ===");
        console.log("credentials:", credentials);

        //!!! REMOVE THIS BLOCK IN PRODUCTION
        if (
          credentials?.email === "test@test.com" &&
          credentials?.password === "test"
        ) {
          console.log("Вход с тестовыми данными");
          return {
            id: "test-user",
            email: credentials.email,
            access: "test-access-token",
            refresh: "test-refresh-token",
          };
        }
        //!!! REMOVE THIS BLOCK IN PRODUCTION

        if (!credentials?.email || !credentials?.password) {
          throw new Error("Email и пароль требуются");
        }

        try {
          const data = await authLogin(credentials.email, credentials.password);
          console.log("authLogin ответ:", data);

          if (!data) {
            throw new Error("Неверные учётные данные");
          }

          return {
            id: data.id,
            access: data.access,
            refresh: data.refresh,
            email: credentials.email,
          };
        } catch (err) {
          console.error("Ошибка при авторизации через credentials:", err);
          throw new Error("Ошибка авторизации");
        }
      },
    }),

    // Добавляем FacebookProvider
    FacebookProvider({
      clientId: process.env.FACEBOOK_CLIENT_ID as string,
      clientSecret: process.env.FACEBOOK_CLIENT_SECRET as string,
      authorization: {
        params: {
          scope: "email,public_profile", // Запрашиваемые разрешения
          // Можно добавить другие параметры, если необходимо
        },
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user, account }) {
      console.log("=== jwt callback ===");
      console.log("Текущий token:", token);
      console.log("user:", user);
      console.log("account:", account);

      // Если авторизуемся через CredentialsProvider, user будет заполнен
      if (user) {
        token.access = user.access;
        token.refresh = user.refresh;
        token.id = user.id;
      }

      // Если пользователь авторизовался через Facebook
      if (account && account.provider === "facebook") {
        console.log("Авторизация через Facebook. Пытаемся обменять токен...");
        try {
          const facebookAccessToken = account.access_token as string;
          const redirect_uri = process.env.FACEBOOK_REDIRECT_URI as string;

          // Отправляем access_token на ваш бэкенд для обмена на токены вашего приложения
          const authData = await authLoginFacebook(
            facebookAccessToken,
            redirect_uri,
          );
          console.log("Ответ бэкенда при facebook авторизации:", authData);

          if (authData) {
            token.access = authData.access;
            token.refresh = authData.refresh;
            token.id = authData.id;
            // Если хотите сохранить ещё и email, если бэкенд вернул
            if (authData.email) {
              token.email = authData.email;
            }
          }
        } catch (error) {
          console.error("Error during Facebook login:", error);
        }
      }

      console.log("jwt callback (выход). Новый token:", token);
      return token;
    },

    async session({ session, token }) {
      console.log("=== session callback ===");
      console.log("Текущий token:", token);
      console.log("session (до изменений):", session);

      if (token?.access) {
        session.user = {
          ...session.user,
          id: token.id as string,
          access: token.access as string,
          refresh: token.refresh as string,
        };
      }
      // Если хотите дополнительно писать email
      if (token?.email) {
        session.user.email = token.email;
      }

      console.log("session (после изменений):", session);
      return session;
    },
  },
  pages: {
    signIn: "/login",
  },
};
